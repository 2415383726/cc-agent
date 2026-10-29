# Interactive answers: static host deployment

The workbench recognizes **assistant native final answers** containing a closed
`pi-visualize` fence. Ordinary HTML/JavaScript code, user messages and tool results
remain inert. It runs an artwork automatically only after both the complete
native answer and that run's trusted `completed` Pi event have arrived.

````text
```pi-visualize
<section data-pi-visualize="1" data-kit-version="1"
  data-title="A readable title" data-description="A short text alternative">
  <!-- HTML, local CSS, classic scripts; no document shell or resource URLs. -->
</section>
```
````

The enclosing `text` fence above is documentation only. Each artwork is limited
to 64 KiB UTF-8, and each answer to two artworks / 128 KiB. Titles permit 120
Unicode characters and descriptions 500. Version 1 currently provides native
HTML/CSS/JavaScript/SVG/canvas only; undeclared libraries are not loaded. Shared
kit assets and the built-in skill are separate follow-up tickets.

## Required response policy

Deploy `dist/visualize/sandbox.html` with **its own** HTTP response header:

```http
Connection-Allowlist: ()
Cache-Control: no-store
Referrer-Policy: no-referrer
```

See `deploy/nginx-visualize.conf.example`. Keep that rule on the exact shell URL.
Do not put the empty Connection-Allowlist on the main workbench document: it
would also prevent normal Dify requests. A meta element cannot supply this
header. Reverse proxies must retain it, redirects are not supported, and the
shell must be served as HTML from the workbench's origin. If the site has an
additional parent CSP, permit the exact shell URL in `frame-src`. The shell's
own CSP allows its nested `blob:` frame and self-contained data images; adding
a narrower inherited script policy can prevent valid artwork scripts running.

`npm run dev` adds these response headers to this URL for local development.
A generic static server and `npm run preview` do **not** install production
headers automatically. Configure the serving proxy before enabling artwork
execution in a production build. Normal chat remains usable without this rule;
artworks show their title, text alternative and deployment explanation.

The parent checks a same-origin, uncached, non-redirected shell response for the
exact empty allowlist before creating a frame. Runtime scripts and assets are
self-contained: Connection-Allowlist prevents the shell from loading even local
external scripts. Future bundled libraries must be supplied as inline code by
the trusted host, not fetched by the artwork.

## Browser support and isolation

The supported compatibility boundary is standard Chromium **154+**. Chromium
154.0.8037.57 is the tested build. Versions 152/153, Firefox, Safari and unknown
WebViews do not execute artwork. Later Chromium versions require ongoing browser
regression testing. A modified browser that disables its security implementation
is outside that support contract. UA/version and response-header checks are
compatibility/deployment gates; they are not a JavaScript security polyfill.
There is no standard JS reflection API proving Connection-Allowlist enforcement.

The trusted static shell is an opaque-origin `allow-scripts` iframe. It creates
another opaque-origin blob frame for author content. The shell's `frame-src
blob:` prevents the inner frame from navigating to a network URL; its inherited
Connection-Allowlist blocks non-Fetch channels such as WebRTC/STUN. The inner CSP
also blocks network resources, connections, nested frames, workers, forms and
base changes. Neither frame grants same-origin, popups, downloads, forms or top
navigation permissions. No credential, model/tool or file-access bridge exists.

Only ready, bounded size and error messages are accepted from the actual frame
and current instance channel. Model-provided IDs and titles do not identify
persistent content. The view uses conversation, platform message, block position
and a content fingerprint; the fingerprint is not an authorization token.

Expansion changes the same frame's available height, retaining its current
parameters. Refresh/reopening creates a new instance with its initial values.
Closing or switching conversation disposes frames, listeners, timers and blob
URLs. Script errors and initialization timeouts show text fallback. Browser
iframes do not provide strong CPU/memory quotas for arbitrary scripts.

## History

Native Dify answers are restored per platform message and merged with that
message's Pi run, replacing clipped log text without replacing earlier answers
or inventing terminal facts. The latest Pi state is not an artwork store.

The current local Dify 1.15 service API returns empty `agent_thoughts` for the
advanced-chat validation app. Therefore a reopened artwork without retained Pi
terminal logs remains unconfirmed and does not auto-run. When the native answer
is complete and the artwork is valid, the user can explicitly choose “查看作品”.
This opens only the saved local artwork, through the same browser/header gates;
it does not change the unknown run status or send an Agent request. Failed,
stopped and other known non-completed runs do not get this action. Recorded real live
Pi events plus native answers exercise the logged-history contract in tests;
this is explicitly different from Dify retaining those events. The minimal
unconfirmed-history view action was moved from ticket 04 into ticket 01 to make
refresh/reopening usable on the actual platform. Ticket 04 retains pagination
and the full abnormal-history/transport acceptance matrix.

Use `/?replay=visualize` for the fixed queue demonstration. Replay uses the same
projection, parser, validation and host as live/history; it never calls a model.
Real Dify and network evidence is recorded in
`../docs/evidence/pi-visualize-ticket01.md`.
