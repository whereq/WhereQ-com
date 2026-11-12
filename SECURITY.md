# Security Policy

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub's
[private vulnerability reporting](https://github.com/whereq/WhereQ-com/security/advisories/new)
on this repository. If that is unavailable to you, open a regular issue that
says only *"security report — please open a private channel"* and nothing
else; you will be asked for details privately.

Please include, as far as you can:

- what the issue is and where in the code it lives,
- how to reproduce it,
- the impact you believe it has,
- any suggested fix.

You should get an acknowledgement within a week. Fixes for confirmed issues are
released as soon as they are ready, and the reporter is credited in the
release notes unless they ask not to be.

## What counts as a vulnerability

- Authentication or authorisation bypass — reaching another user's data, or an
  admin-only surface without the right role.
- Injection — SQL injection, command injection, or anything that lets
  untrusted content take over the backend.
- Secret exposure — a credential, token or private key committed to the
  repository or baked into an image.
- Unsafe defaults — a deployment that is exposed by default.

## What does not

- Missing hardening you did not ask for. We welcome hardening pull requests.
- A data source returning the wrong place. That is a quality issue.
- Rate-limit or abuse issues in a third-party service.
- Denial of service through sheer request volume against your own deployment.

## Threat model

whereq.com is designed to be run by the person who deploys it, on their own
infrastructure. A few consequences worth stating plainly:

**The backend trusts its own database and its own configuration.** Anything
that reaches the API as a request is untrusted; anything already in the
database was put there by this application or by an operator. SQL is built
through the ORM or bound parameters — a request field must never be
interpolated into a statement.

**The OIDC provider is the trust boundary for identity.** The backend
verifies an RS256 token against the provider's JWKS, checks the issuer, and
checks `azp` against the configured client. A token that fails any of those
is rejected. The provider's *contents* are not otherwise interpreted: claims
become a local `users` row and nothing else.

**The crawler consumes untrusted input.** RSS and JSON feeds are third-party
content. They are parsed as data — never executed, never rendered as HTML
without escaping.

**Geocoding is untrusted input too.** A provider can return anything. That is
why the placement step has a distance guard: a candidate more than 20 km (or
60 km, for a curated place) from the content's own city centre is rejected
rather than pinned.

**Your deployment is your responsibility.** Put the API behind
authentication, terminate TLS in front of it, and keep the database off the
public internet.

## Hardening notes for operators

- Set a strong `POSTGRES_PASSWORD` and a random `SECRET_KEY`. The Compose
  stack **refuses to start** without them rather than falling back to a
  default — that guard is deliberate, do not remove it.
- The `postgres` service does not publish a port to the host. If you add one,
  remove it again before exposing the stack to anything.
- Keep `GOOGLE_MAPS_SERVER_KEY`, `GOOGLE_MAPS_API_KEY`,
  `WHEREQ_CLOUD_API_KEY` and `KEYCLOAK_ADMIN_CLIENT_SECRET` out of version
  control. `.env` is gitignored; use your platform's secret store where you
  have one.
- `NOMINATIM_EMAIL` should be a real contact address. The OSM usage policy
  asks automated clients to identify themselves.
- Set `APP_ENV=production` for anything reachable from outside. In
  development mode the backend refuses to start against a non-local database
  — it would echo every statement's bound parameters, emails and tokens
  included.
- Rotate the database password if this repository was ever deployed with the
  example values in a non-local environment.
