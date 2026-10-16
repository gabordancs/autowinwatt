# Runtime artifact storage

Generated WinWatt mapping graphs, checkpoints, logs, screenshots, PDFs, WWP
projects and customer-related certificate outputs are not source code and are
not stored in Git.

The cleanup archive is stored outside this repository. Its `manifest.json`
contains every archived relative path, byte count and SHA-256 digest. Verify it
with the adjacent `manifest.sha256` before restoring files.

The repository continues to track the Python source, tests, compact capability
registry and curated certification knowledge. Runtime evidence is regenerated
or restored from the external archive when a forensic reproduction is needed.

To create another archive from the currently tracked artifact set:

```powershell
.\scripts\archive_git_artifacts.ps1 -Destination M:\AWA\YYYYMMDD
```

The script refuses destinations inside the repository and existing output
directories. It copies files only; it does not modify the Git index or delete
the working copies.

The verified 2026-10-16 cleanup record, including the manifest and pre-cleanup
Git-bundle hashes, is stored in `docs/artifact_archive_20261016.json`.
