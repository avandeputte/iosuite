# Hosting on Cloudflare Pages

iosuite.iothing.net is a Cloudflare Pages project, deployed by this repository's workflow with Wrangler (direct
upload), the same way as ham.iothing.net. Cloudflare's own Git integration is not used: the build runs in GitHub
Actions, because it checks the pages against the apps' repositories first.

This is the one-time setup. After it, every push to `main` (and a nightly run) publishes the site.

## 1. Create the Pages project

Either in the dashboard: **Workers & Pages › Create › Pages › Upload assets** (Direct Upload), project name
**`iosuite`**, and upload the `site/` folder of a local build once.

Or from a shell, after `sh build.sh`:

```bash
npx wrangler login
npx wrangler pages project create iosuite --production-branch main
npx wrangler pages deploy site --project-name iosuite --branch main
```

The project's production branch must be `main`: the workflow deploys with `--branch main`, so its uploads are
production deployments. The site is then at `https://iosuite.pages.dev`.

## 2. The custom domain

In the project: **Custom domains › Set up a custom domain** › `iosuite.iothing.net`. Since `iothing.net` is a zone in
the same Cloudflare account, Cloudflare adds the `CNAME iosuite → iosuite.pages.dev` record itself and issues the
certificate; it is live within a few minutes.

## 3. The API token

**My Profile › API Tokens › Create Token › Create Custom Token**:

| | |
| --- | --- |
| Name | `iosuite-docs deploy` |
| Permissions | Account › **Cloudflare Pages** › **Edit** |
| Account resources | Include › your account |

(The token used for ham.iothing.net has the same permission and works here too, if you'd rather reuse it.)

## 4. The repository secrets

In GitHub: **avandeputte/iosuite-docs › Settings › Secrets and variables › Actions › New repository secret**:

| Secret | Value |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | the token from step 3 |
| `CLOUDFLARE_ACCOUNT_ID` | the account id, on the right of the account's **Workers & Pages** overview |

Or with the GitHub CLI:

```bash
gh secret set CLOUDFLARE_API_TOKEN --repo avandeputte/iosuite-docs
gh secret set CLOUDFLARE_ACCOUNT_ID --repo avandeputte/iosuite-docs
```

Until both are set, the workflow still builds and checks every push but skips the deploy step.

## 5. Deploy

**Actions › build › Run workflow** on `main`, or push to `main`. The deploy step prints the deployment's URL.

## What the site sends

`landing/_headers` becomes Cloudflare Pages' headers file: `nosniff` and a referrer policy everywhere, an hour's cache
for the screenshots and a year's for MkDocs' fingerprinted assets. `landing/404.html` is served for any address that
does not exist. There are no Pages Functions and nothing server-side.

## Troubleshooting

- **`Project not found`** in the deploy step: the project name must be exactly `iosuite`, in the account of
  `CLOUDFLARE_ACCOUNT_ID`.
- **`Authentication error [code: 10000]`**: the token lacks Cloudflare Pages › Edit on that account.
- **The domain shows an old version**: open the project's Deployments; the production one must be from branch `main`.
