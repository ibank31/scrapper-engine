# Agent Entry Point

Sebelum mengubah repository ini, baca manual lengkap di [`docs/AGENT_HANDOFF.md`](docs/AGENT_HANDOFF.md) dan status singkat di [`STATUS.md`](STATUS.md).

## Non-negotiable rules

- Campaign rules adalah source of truth. Jangan memakai asumsi global jika detail campaign tersedia.
- Material publik yang dicantumkan campaign harus diambil dan dicatat di `assets.json` dengan checksum.
- Pertahankan `materials/RULES_SNAPSHOT.md` dan provenance setiap asset.
- Proses semua video source yang berhasil diambil, bukan hanya source pertama.
- Upload dan review queue harus berisi maksimal dua kandidat final per job; pilih lintas semua source setelah relevance gate.
- Pisahkan technical validation dari campaign relevance validation.
- Clip yang salah konteks harus diblokir, walaupun format MP4-nya valid.
- Pertahankan face-aware crop, subtitle phrase-level, safe zone, dan visual-quality checks.
- Auto-publish tetap disabled. Manusia hanya menyetujui preview final.
- Jangan pernah memasukkan token, secret, cookie, atau credential ke source, fixture, log, atau dokumentasi.
- Setiap perubahan parser, worker, validator, atau renderer harus disertai regression test.

## Minimum verification

```bash
python3 -m py_compile core/*.py modules/*/*.py worker/*.py
python3 -m unittest discover -s tests -v
python3 -m compileall -q core modules worker
python3 -m pip check
git diff --check
```
