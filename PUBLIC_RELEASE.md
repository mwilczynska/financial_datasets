# Public release checklist

This document defines the release gates for the public repository under the
GitHub handle mwilczynska.

## Identity policy

The public repository may expose:

- the GitHub handle mwilczynska;
- the repository URL under that handle;
- a GitHub-generated noreply commit address.

It must not expose:

- a personal email address or real-name commit identity;
- local filesystem paths;
- private project names or downstream application filenames;
- personal location, employer, phone number, or other profile details.

Review the GitHub account profile and repository-owner settings separately.
Keep public email, location, employer, website, bio, and contact fields limited
to information intentionally disclosed.

## Public data scope

This release intentionally includes:

- final CSV and Parquet outputs under data/processed/;
- normalized interim CSV outputs under data/interim/;
- small validation fixtures under tests/fixtures/.

It intentionally excludes downloaded source caches under sources/raw/ except
for the explanatory README. Raw-source publication requires a separate
source-by-source permission review.

## Release gates

Before changing repository visibility:

1. Preserve the complete private repository, including current history and
   uncommitted work, in a separate private archive.
2. Sanitize documentation and generated metadata to use repository-relative
   paths.
3. Review the published outputs and source-specific redistribution caveats;
   keep raw source caches out unless their terms permit publication.
4. Confirm the public Git identity is mwilczynska with a GitHub noreply address.
5. Review the GitHub account profile and repository-owner settings for unintended
   public details.
6. Run the audit:

       python src/audit_public_release.py

7. Run the validation suite from a clean checkout:

       python -m pytest -q tests/validation

8. Review the exact staged file list. Include the intended data outputs only;
   do not publish private branches, tags, releases, issue attachments, Actions
   artifacts, or old history.
9. Make the repository public only after all gates pass.
10. Clone the public repository while signed out and repeat the audit.

The audit must pass against both the candidate tree and the complete history
that will be visible publicly.
