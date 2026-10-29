# Fixed-artifact HTTP diagnostics: source preparation

Status: **first diagnostic retained; one corrected-transport diagnostic authorized**. Preparation is isolated on
`lead/cloud-natural-wheel-diagnostics-20261029`, based on study control
`c699d9600ae16f955d523af1a3c303604b331743`. The study branch, both failed
preflight runs, original local harness and metadata freeze remain unchanged.
Root concretely reviewed source `438b8457` before authorizing the separate
single diagnostic activation recorded below.

Study run 40804360782 passed 119 pure contracts, then its registered artifact
helper raised `HTTPError`. Wheel installation, freeze and study execution were
skipped. Its 2,798-byte original negative ZIP, JUnit, decoded job log and metadata
remain externally retained. Failure receipt SHA-256 is
`517f395d98c7c314274243a640bcb7f4c3367833a3da6cd312b2e5432d42019f`.
That source did not record HTTP status or request substage, so neither is
inferred after the fact. Both study preflights had zero study exposure.

## Closed diagnostic sequence

The only artifact remains 12861488234 from registered run 40791402289/control
`27f0f3d1` in `YotsuBotfds/Chronicler`. The existing closed policy supplies the
same official name, ZIP/manifest/wheel/native digests, sizes, schemas and exact
C76 producer/crate/dependency inputs. No CLI artifact, URL, digest, policy or
credential override is introduced.

After pure contracts, perform one official metadata GET. Validate its fixed
identity/digest/size/expiry first. Only a successful matching response permits
the official ZIP GET and its single registered HTTPS Azure redirect. Record
only closed stage names, numeric HTTP status (or null when unavailable) and
provider kinds `github_api`, `azure_blob`, `unregistered` or `local_verifier`.
The output also identifies the fixed artifact/run and boolean verification
standing. It contains no URL, hostname, token, header or response-body text.

On 401/403/404, retain the sanitized failure and stop. There is no retry,
alternate host, artifact, authentication route, broader scope or new credential
request. Transport errors and identity/byte failures also stop. Any assessment
of a fresh source-qualified native build would be separate prospective work,
not a route around a denied artifact request.

The helper closes HTTP error responses without reading them. Its actual urllib
redirect handler also closes without draining the redirect body, including on
rejected redirects. It follows only the exact API ZIP endpoint to an approved
Azure blob target and strips authorization, proxy authorization and cookies.
Location length, metadata/ZIP reads and decompression/member sets remain
bounded. An owned absolute 120-second timer also stops trickling responses that
never reach a socket timeout; its failure is sanitized and timer ownership is
restored. Only a fully matching official ZIP and its matching members
may be retained; unexpected 200/error bodies are not saved.

Diagnostic mode emits `diagnostics.json`, never an installable
`verification.json`. It imports no native runtime, installs no native wheel,
builds nothing and invokes no freeze, worker, reader or simulation command.
The ordinary future fetch path separately gains the same sanitized failure
record; the already-failed study controls are not modified or rerun.

## Inactive workflow and verification

The dedicated workflow accepts only its exact diagnostic branch and workflow
path. Its initial job guard additionally contains `false`; there is no manual
dispatch or broad trigger. It uses separate exact-C76 and control checkouts,
CPython 3.13.17, locked Python test dependencies, one affinity CPU/thread caps,
then guarded pure tests before one diagnostic helper invocation. The existing
GitHub token has read-only contents/actions permissions and is exported only
to that diagnostic step. JUnit/guard records and sanitized diagnostic output
are uploaded even on failure. No study workflow is activated by this source.

Synthetic tests cover 401/403/404 at both providers, metadata-before-ZIP ordering,
no fallback, signed-URL/token/header/body redaction, actual redirect handler
close-without-read behavior, credential stripping, unregistered endpoints and
retention only of verified payloads. Static workflow contracts cover its closed
inactive/activated states, test-before-request ordering and scope restrictions.
These tests perform no network request or runtime qualification. Independent
source review clears the transport fix and inactive workflow; root's concrete
review and any actual diagnostic activation remain separate.

Final focused verification passed **153 guarded pure tests in 1.22 seconds**,
with no native import, runtime-factory or blocked-I/O attempt. Actionlint 1.7.12
and diff checks passed. Independent source review cleared the final transport,
redaction, absolute timer and timer-finalization transaction. Disarm failures
retain incomplete positive attempts, restore ownership and emit safe negative
records without repeating HTTP. These checks used no-native Python 3.13.5,
CPU2, hash seed zero and thread caps one. No actual network probe, native
installation/build, freeze or study execution occurred.

## Single read-only activation

Root reviewed helper transport, redaction and timer-finalization behavior,
the complete workflow and both closed workflow states at source
`438b8457dda827572a0d647f89f5d27b7e9bc822`. It authorized exactly one diagnostic
push on this separate branch. Activation removes only the false gate and
changes workflow names/comments and this record; helper, tests, scientific
protocols, native policy and study runner remain byte-identical to that source.
The final 153 guarded selection, actionlint and diff checks must pass against
the activated workflow bytes before the single push.

The fixed sequence remains metadata GET, then matching-metadata admission,
then only if permitted the registered ZIP GET and its single Azure redirect.
On 401/403/404 it must publish the sanitized result and stop; no route, host,
token, scope, credential or retry change is authorized. The diagnostic cannot
invoke installation, freeze, study execution or native builds. The study branch
stays at `c699d960`, with both earlier failures retained. There is no automatic
diagnostic or study rerun, and this activation claims no network outcome yet.

## First diagnostic result and corrected transport

The first read-only diagnostic was control
`ba9bebff71ccc8070fb6b21998f1de0e12ad5754`, run 40806131240/job 123225405588.
All 153 guarded contracts passed remotely in 3.76 seconds. Its exact observations
were metadata GET 200 from GitHub, ZIP GET 302 from GitHub, then Azure redirect
GET 400. Metadata identity passed; the archive remained unverified. The helper
stopped, retained sanitized evidence and made no alternate request or retry.
No installation, freeze, native build or study execution occurred.

Original artifact 12868541609 was 4,457 bytes, SHA-256
`8864d08b86fc91a803236f3666ad7bd2479c2b285f503bade57ce578aaf45267`.
The verified result receipt is
`219dc0f5093062eba145919026b8e179a266a151685ca2a3db0683b9d036da4c`,
retained with original ZIP/JUnit/guard/JSON/log at
`/workspace/chronicler-natural-remote-evidence/wheel-diagnostic-ba9bebff-001`.
No 403 or error body was observed/retained by this diagnostic. Earlier study
control c699's unlogged HTTP status remains unknown.

Root then reproduced a concrete transport defect without opening a connection:
urllib's real header preparation adds an unredirected origin Host, and the
helper's `header_items()` copy forwarded that Host to the destination. The
second real header-preparation pass preserved the wrong Host. Authorization
was absent, but origin Accept/API-version/custom headers also crossed origins.
This proves the header defect; it does not retrospectively establish the full
cause of the observed 400 response.

The corrected redirect creates a fresh request carrying only the fixed known
User-Agent. It inherits no original header; urllib derives the destination Host
itself. The endpoint, provider whitelist, authentication scope, artifact pins,
redaction, body handling, timeout and denial-stop rules are unchanged. The
regression uses the real `HTTPHandler.do_request_` before and after redirect,
failed on the old implementation and passes after correction, with zero network
calls. Before/after proof and the original failing test log are retained at
`/workspace/chronicler-natural-remote-evidence/redirect-host-reproduction-001`.

Root authorized exactly one corrected-source **read-only transport diagnostic**.
Only helper/header regression, workflow comment marker and this record change.
The actual study branch remains c699; no study, installation, build or freeze
is authorized. The complete guarded selection, actionlint, diff checks and
independent source review must pass before one push. The corrected request must
either verify the exact registered archive or retain its safe failure and stop.
No automatic retry, broader route or new credential is permitted.
