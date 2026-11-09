# Hosting on Cloudflare Workers

iosuite.iothing.net is a Cloudflare Worker named `iosuite` that serves the built site as static assets. No code runs
in it: every request is answered with a file from `site/`. This repository's workflow builds the site in GitHub
Actions (it checks the pages against the apps' repositories first) and deploys it with Wrangler. Cloudflare's own Git
integration is not used.

Everything about the Worker is in [`wrangler.jsonc`](wrangler.jsonc): its name, the `site/` folder, the 404 page and
the custom domain. So the one-time setup is only the token and the two secrets; the first deploy creates the Worker
and attaches the domain.

## 1. The API token

**My Profile › API Tokens › Create Token › Create Custom Token**:

| | |
| --- | --- |
| Name | `iosuite-docs deploy` |
| Permissions | Account › **Workers Scripts** › **Edit** |
| | Zone › **Workers Routes** › **Edit** |
| | Zone › **DNS** › **Edit** |
| Account resources | Include › your account |
| Zone resources | Include › Specific zone › `iothing.net` |

The two zone permissions are for the custom domain: Wrangler adds the `iosuite` DNS record and the route itself.

## 2. The repository secrets

In GitHub: **avandeputte/iosuite-docs › Settings › Secrets and variables › Actions › New repository secret**:

| Secret | Value |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | the token from step 1 |
| `CLOUDFLARE_ACCOUNT_ID` | the account id, on the right of the account's **Workers & Pages** overview |

Or with the GitHub CLI:

```bash
gh secret set CLOUDFLARE_API_TOKEN --repo avandeputte/iosuite-docs
gh secret set CLOUDFLARE_ACCOUNT_ID --repo avandeputte/iosuite-docs
```

Until both are set, the workflow still builds and checks every push but skips the deploy step.

## 3. Deploy

**Actions › build › Run workflow** on `main`, or push to `main`. Or by hand, from a clone:

```bash
sh build.sh
npx wrangler login
npx wrangler deploy
```

The site is then at `https://iosuite.iothing.net` (the certificate can take a few minutes the first time), and also
at the Worker's `workers.dev` address.

## What the site sends

`landing/_headers` becomes the Worker's headers file: `nosniff` and a referrer policy everywhere, an hour's cache for
the screenshots and a year's for MkDocs' fingerprinted assets. `landing/404.html` is served for any address that does
not exist.

## Troubleshooting

- **`Authentication error [code: 10000]`**: the token lacks Workers Scripts › Edit on the account of
  `CLOUDFLARE_ACCOUNT_ID`.
- **The deploy fails on the custom domain**: the token lacks the zone permissions on `iothing.net`, or an older DNS
  record for `iosuite.iothing.net` (such as a CNAME to a Pages project) is in the way; delete that record and deploy
  again.
- **`/docs/` is missing**: the deploy ran without a build; `wrangler deploy` uploads whatever is in `site/`, so run
  `sh build.sh` first.
