# Fixed-artifact HTTP diagnostics: source preparation

Status: **inactive; no diagnostic request has run**. Preparation is isolated on
`lead/cloud-natural-wheel-diagnostics-20261029`, based on study control
`c699d9600ae16f955d523af1a3c303604b331743`. The study branch, both failed
preflight runs, original local harness and metadata freeze remain unchanged.
Root must review this concrete source before activating its separate workflow.

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
