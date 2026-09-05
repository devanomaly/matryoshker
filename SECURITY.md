# Security Policy

## Threat model

Matryoshker's pipeline (`extractor/`, `pipeline/`) makes no network calls at runtime.
The only time it touches the network at all is the one-off `npm ci --ignore-scripts` in
`extractor/`, which installs lockfile-pinned dependencies. Extraction and every pipeline
step run entirely offline, read-only against the target repository, and write only under
the `--out` / `--extract-out` paths you pass on the command line — never into the target
repository itself.

The output, `matryoshker.html`, is a single self-contained HTML file with zero external
dependencies except a Google Fonts `<link>`. It embeds a JSON snapshot of whatever
structural data was extracted; it does not fetch anything at view time and does not
transmit the embedded data anywhere.

Given that shape, the most relevant risks are: a vulnerable dependency reaching the
extractor's toolchain, or a change that makes a script write outside its declared output
directory or accidentally into the target repository.

## Supported versions

The `main` branch is the only supported version. There are no long-term-support
branches at this stage.

## Reporting a vulnerability

Please report security issues using
[GitHub's private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
on this repository (the "Security" tab → "Report a vulnerability"), rather than opening a
public issue. This lets a fix be prepared before the details are public.

If you believe an issue is not sensitive (for example, a dependency advisory with no
exploit path in how this project uses it), a regular GitHub issue is fine.
