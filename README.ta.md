# nxmirror-db (Python) — தமிழ் வழிகாட்டி

NxMirror DB (NxDB) கிளவுட் தரவுத்தளத்தை Python SDK மூலம் இணைத்து
பயன்படுத்துவதற்கான **முழுமையான, நேரடியாக இயக்கக்கூடிய உதாரணங்கள்**.

ஆங்கில முழு வழிகாட்டி: **[README.md](README.md)**

## 1. நிறுவுதல் (Install)

```bash
pip install nxmirror-db
# அல்லது GitHub-லிருந்து:
pip install git+https://github.com/crossberry-in/nxmirror-db-python.git
```

Python 3.8+ தேவை. **வேறு எந்த dependency-யும் இல்லை** — Python இன்
standard library மட்டுமே பயன்படுகிறது.

## 2. விரைவாகத் தொடங்குவது (Quick start)

```bash
python scripts/live_e2e.py   # demo account + 2 தரவுத்தளங்கள் உருவாக்கி 66 சோதனைகள் இயக்கும்
```

கைமுறையாக:

```bash
python examples/00_setup_database.py             # demo account + sqlite & nosql தரவுத்தளங்கள் → .env.local
python examples/01_connect.py                    # இணைப்பு + introspection
python examples/02_sql_crud.py                   # SQL + query builder
python examples/03_nosql_crud.py                 # NoSQL documents
python examples/04_file_storage.py               # கோப்பு upload/download
python examples/05_error_handling.py             # பிழை கையாளுதல்
python examples/06_realtime_changes.py           # changes feed + watch()
python examples/00_setup_database.py --cleanup   # முடிந்ததும் நீக்குதல்
```

உங்கள் சொந்த தரவுத்தளம் ஏற்கனவே இருந்தால்: `.env.example`-ஐ `.env.local` என
நகலெடுத்து, dashboard-ல் கிடைக்கும் `NXDB_ID` மற்றும் `NXDB_PASSWORD`-ஐ நிரப்பவும்.

## 3. இணைக்கும் முறை (Connect)

```python
from nxmirror_db import connect

db = connect(database_id="nxdb-…", password="…")

res = db.query("SELECT * FROM users WHERE active = ?", [True])
print(res["rows"])
```

- `password` — முழு அணுகல்; **நம்பகமான server-களில் மட்டும்**
- `token="nxdb_…"` — scoped API token (permission-set உடன்)
- `appId` + `appToken` — embedded/browser செயலிகளுக்கு

## 4. SQL vs NoSQL — மிக முக்கியம்

| தரவுத்தள engine | பயன்படுத்துவது | உதாரணம் |
| --- | --- | --- |
| `sqlite` | `db.query()`, `db.exec()`, `db.table()` | `02_sql_crud.py` |
| `nosql` | `db.nosql.insert/find/get/update/…` | `03_nosql_crud.py` |

தவறான இரண்டை கலந்தால் SDK உடனேயே `wrong_engine` பிழையை தரும் (நெட்வொர்க்
அனுப்பாமலேயே). File storage (`db.storage.*`) இரண்டு engine-லும் வேலை செய்யும்.

## 5. கோப்பு storage — சுருக்கம்

```python
file = db.storage.upload("images/photo.jpg", image_bytes,
                         mime="image/jpeg", public=True)

print("file id:", file["id"])
# பொது URL: https://nxmirror.netlify.app/api/db/storage/download/<fileId>?db=<databaseId>

back = db.storage.download(file["id"])                 # raw bytes
url = db.storage.signed_url(file["id"], 900)           # private — 5–60 நிமிடம்
```

3.4 MB-க்கு மேல் உள்ள கோப்புகள் தானாகவே resumable part uploads ஆக அனுப்பப்படும்
(அதிகபட்சம் 50 MB). `on_progress=lambda p: print(p["pct"])` மூலம் முன்னேற்றத்தைக்
காட்டலாம்.

## 6. பிழைகள் — code வாங்கி கையாளுங்கள்

```python
from nxmirror_db import NxError

try:
    db.query("SELECT * FROM nope")
except NxError as e:
    print(e.code, e.status, e)
    # unauthorized / wrong_database / wrong_engine / sql_error / ambiguous_match …
```

## 7. பாதுகாப்பு அடிப்படை விதிகள்

- Database password-ஐ **ஒருபோதும்** browser அல்லது mobile app bundle-இல்
  வைக்காதீர்கள் — `appId` + `appToken` அல்லது குறுகிய கால scoped token பயன்படுத்துங்கள்.
- Token-களுக்கு தேவையான குறைந்த permission-ஐ மட்டும் கொடுங்கள்.
- Chat அல்லது code-ல் token ஒட்டினால் உடனே revoke செய்யவும்.

## 8. இணைப்புகள்

- Platform: <https://nxmirror.netlify.app>
- Platform docs: <https://nxmirror.netlify.app/docs>
- JS SDK (npm): <https://www.npmjs.com/package/nxmirror-db>
- JS examples repo: <https://github.com/crossberry-in/db-example>
- முழு ஆங்கில வழிகாட்டி: [README.md](README.md)

## License

MIT — [LICENSE](LICENSE) பார்க்கவும்.
