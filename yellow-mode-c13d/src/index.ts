/**
 * GitHub OAuth proxy for Decap CMS.
 *
 * Required secrets (set via `wrangler secret put` or Cloudflare dashboard):
 *   GITHUB_CLIENT_ID     — from your GitHub OAuth App
 *   GITHUB_CLIENT_SECRET — from your GitHub OAuth App
 *
 * GitHub OAuth App settings:
 *   Homepage URL:     https://xBwomp.github.io/central_data_agency
 *   Callback URL:     https://yellow-mode-c13d.xbwomp.workers.dev/callback
 *
 * Flow:
 *   1. Decap CMS opens a popup to /auth
 *   2. This worker redirects to GitHub's OAuth authorize page
 *   3. GitHub redirects back to /callback with ?code=...
 *   4. This worker exchanges the code for an access token
 *   5. Returns an HTML page that postMessages the token back to the CMS popup opener
 */

interface Env {
	GITHUB_CLIENT_ID: string;
	GITHUB_CLIENT_SECRET: string;
}

export default {
	async fetch(req: Request, env: Env): Promise<Response> {
		const url = new URL(req.url);

		if (url.pathname === '/auth') {
			const params = new URLSearchParams({
				client_id: env.GITHUB_CLIENT_ID,
				scope: 'repo,user',
				state: crypto.randomUUID(),
			});
			return Response.redirect(
				`https://github.com/login/oauth/authorize?${params}`,
				302,
			);
		}

		if (url.pathname === '/callback') {
			const code = url.searchParams.get('code');
			if (!code) {
				return new Response('Missing code parameter', { status: 400 });
			}

			const tokenRes = await fetch('https://github.com/login/oauth/access_token', {
				method: 'POST',
				headers: {
					Accept: 'application/json',
					'Content-Type': 'application/json',
				},
				body: JSON.stringify({
					client_id: env.GITHUB_CLIENT_ID,
					client_secret: env.GITHUB_CLIENT_SECRET,
					code,
				}),
			});

			const data = (await tokenRes.json()) as { access_token?: string; error?: string };

			if (data.error || !data.access_token) {
				return new Response(`OAuth error: ${data.error ?? 'no token returned'}`, {
					status: 400,
				});
			}

			// Decap CMS expects this exact postMessage format.
			const message = `authorization:github:success:${JSON.stringify({
				token: data.access_token,
				provider: 'github',
			})}`;

			const html = `<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
<script>
(function () {
  var authMsg = ${JSON.stringify(message)};
  if (!window.opener) { return; }
  // Step 1: send handshake
  window.opener.postMessage('authorizing:github', '*');
  // Step 2: wait for handshake reply, then send token
  window.addEventListener('message', function handler(e) {
    if (e.data === 'authorizing:github') {
      window.removeEventListener('message', handler);
      window.opener.postMessage(authMsg, '*');
      window.close();
    }
  });
})();
</script>
</body>
</html>`;

			return new Response(html, {
				headers: { 'Content-Type': 'text/html; charset=utf-8' },
			});
		}

		return new Response('Not found', { status: 404 });
	},
} satisfies ExportedHandler<Env>;
