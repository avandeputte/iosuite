/* HTTP to the start page: its address and the device's app password (Authorization: Bearer), JSON in and out. An
 * https:// address is checked against the usual certificate authorities (esp_crt_bundle). */
#include <ctype.h>
#include <string.h>
#include "esp_crt_bundle.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "wall.h"

bool api_normalize(const char *in, char *out, size_t n)
{
    while (*in && isspace((unsigned char)*in)) in++;
    char tmp[160];
    strlcpy(tmp, in, sizeof tmp);
    size_t l = strlen(tmp);
    while (l && (isspace((unsigned char)tmp[l - 1]) || tmp[l - 1] == '/' || tmp[l - 1] == '#')) tmp[--l] = 0;
    if (!l || strchr(tmp, ' ')) return false;
    /* the scheme and the host in lower case ("Start.Example.com"), the rest as typed */
    char *host = strstr(tmp, "://");
    host = host ? host + 3 : tmp;
    for (char *p = tmp; *p && (p < host || *p != '/'); p++) {
        *p = (char)tolower((unsigned char)*p);
    }
    if (!strncmp(tmp, "http://", 7) || !strncmp(tmp, "https://", 8)) {
        strlcpy(out, tmp, n);
    } else {
        snprintf(out, n, "http://%s", tmp);
    }
    return strlen(out) > 8;
}

api_resp_t api_request(const char *method, const char *path, const char *body, size_t max, const char *base)
{
    return api_request_auth(method, path, body, max, base, NULL);
}

api_resp_t api_request_auth(const char *method, const char *path, const char *body, size_t max, const char *base,
                            const char *authorization)
{
    api_resp_t r = {0};
    const char *server = base ? base : S.server;
    if (!server[0]) {
        r.status = -1;
        strlcpy(r.why, "No address set", sizeof r.why);
        return r;
    }
    if (net_state() != NET_UP) {
        r.status = -1;
        strlcpy(r.why, "No Wi-Fi", sizeof r.why);
        return r;
    }
    char url[384];
    snprintf(url, sizeof url, "%s%s", server, path);
    esp_http_client_config_t c = {
        .url = url,
        .timeout_ms = 15000,
        .buffer_size = 4096,
        .buffer_size_tx = 2048,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .max_redirection_count = 3,
        .user_agent = "ioWall " BOARD_NAME,
        .keep_alive_enable = true,
    };
    bool post = !strcmp(method, "POST");
    c.method = post ? HTTP_METHOD_POST : !strcmp(method, "PUT") ? HTTP_METHOD_PUT : !strcmp(method, "DELETE") ? HTTP_METHOD_DELETE : HTTP_METHOD_GET;
    esp_http_client_handle_t h = esp_http_client_init(&c);
    if (!h) {
        r.status = -1;
        strlcpy(r.why, "Out of memory", sizeof r.why);
        return r;
    }
    char auth[200];
    if (authorization) {
        esp_http_client_set_header(h, "Authorization", authorization);
    } else if (!base && S.token[0]) {
        snprintf(auth, sizeof auth, "Bearer %s", S.token);
        esp_http_client_set_header(h, "Authorization", auth);
    }
    esp_http_client_set_header(h, "Accept", "application/json, image/jpeg");
    int blen = body ? (int)strlen(body) : 0;
    if (body) {
        esp_http_client_set_header(h, "Content-Type", "application/json");
    }
    esp_err_t e = esp_http_client_open(h, blen);
    if (e != ESP_OK) {
        r.status = -1;
        snprintf(r.why, sizeof r.why, "Cannot reach %s (%s)", server, esp_err_to_name(e));
        esp_http_client_cleanup(h);
        return r;
    }
    if (blen && esp_http_client_write(h, body, blen) != blen) {
        r.status = -1;
        strlcpy(r.why, "The request was cut off", sizeof r.why);
        esp_http_client_cleanup(h);
        return r;
    }
    int64_t clen = esp_http_client_fetch_headers(h);
    r.status = esp_http_client_get_status_code(h);
    /* a redirect on a GET: follow it (esp_http_client_open does not by itself) */
    for (int hop = 0; hop < 3 && (r.status == 301 || r.status == 302 || r.status == 303 || r.status == 307 || r.status == 308) && !post; hop++) {
        esp_http_client_set_redirection(h);
        esp_http_client_close(h);
        if (esp_http_client_open(h, 0) != ESP_OK) break;
        clen = esp_http_client_fetch_headers(h);
        r.status = esp_http_client_get_status_code(h);
    }
    char *ct = NULL;
    if (esp_http_client_get_header(h, "Content-Type", &ct) == ESP_OK && ct) {
        strlcpy(r.type, ct, sizeof r.type);
    }
    size_t cap = clen > 0 ? (size_t)clen + 1 : 16384;
    if (cap > max + 1) cap = max + 1;
    r.body = heap_caps_malloc(cap, MALLOC_CAP_SPIRAM);
    if (!r.body) {
        r.status = -1;
        strlcpy(r.why, "Out of memory", sizeof r.why);
        esp_http_client_cleanup(h);
        return r;
    }
    for (;;) {
        if (r.len + 1 >= cap) {
            if (cap > max) {
                break;  /* more than we take: what came is kept, cut */
            }
            size_t ncap = cap * 2 > max + 1 ? max + 1 : cap * 2;
            char *nb = heap_caps_realloc(r.body, ncap, MALLOC_CAP_SPIRAM);
            if (!nb) break;
            r.body = nb;
            cap = ncap;
        }
        int got = esp_http_client_read(h, r.body + r.len, cap - 1 - r.len);
        if (got < 0) {
            r.status = -1;
            strlcpy(r.why, "The answer was cut off", sizeof r.why);
            break;
        }
        if (got == 0) {
            if (esp_http_client_is_complete_data_received(h) || clen <= 0) break;
            break;
        }
        r.len += got;
    }
    r.body[r.len] = 0;
    esp_http_client_close(h);
    esp_http_client_cleanup(h);
    if (r.status >= 400 && !r.why[0]) {
        if (r.status == 401) strlcpy(r.why, "Not signed in (the app password was removed?)", sizeof r.why);
        else if (r.status == 403) strlcpy(r.why, "Not allowed for this account", sizeof r.why);
        else snprintf(r.why, sizeof r.why, "The start page answered %d", r.status);
        /* {"detail": "..."}: the start page's own words */
        char *d = strstr(r.body, "\"detail\"");
        if (d) {
            d = strchr(d + 8, '"');
            if (d) {
                char *end = strchr(d + 1, '"');
                if (end && end - d - 1 < (int)sizeof r.why) {
                    memcpy(r.why, d + 1, end - d - 1);
                    r.why[end - d - 1] = 0;
                }
            }
        }
    }
    if (r.status == 200 && strstr(r.type, "text/html")) {
        /* a sign-in page in the way: Cloudflare Access, or not the start page at all */
        r.status = -2;
        strlcpy(r.why, "A web page answered instead of the start page (Cloudflare Access?). Use its address inside your network.", sizeof r.why);
    }
    return r;
}

void api_free(api_resp_t *r)
{
    if (r->body) {
        heap_caps_free(r->body);
    }
    r->body = NULL;
    r->len = 0;
}
