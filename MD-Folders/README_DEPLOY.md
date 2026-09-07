# Deployment Guide for Railway + Render

## 1. What goes where

- **Railway**: host your MySQL database
- **Render**: host the Flask web app

This repo is a Flask + Socket.IO app. It is compatible with Render using `gunicorn` + `eventlet` and Railway as the MySQL provider.

---

## 2. Render service setup

1. Create a new **Web Service** on Render.
2. Connect it to this Git repository.
3. Set the following build and start commands:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn -k eventlet -w 1 -b 0.0.0.0:$PORT app:app`
4. Add these environment variables in Render:
   - `FLASK_ENV=production`
   - `SECRET_KEY=<your-strong-secret>`
   - `DATABASE_URL=<railway-database-url>`
   - `CORS_ORIGINS=https://<render-service>.onrender.com`
5. If you want uploads to persist between deployments, enable a connected disk or use an external storage provider. Otherwise, uploaded files will be ephemeral.

---

## 3. Railway database setup

1. Create a new **MySQL** database on Railway.
2. Copy the provided connection string and use it as `DATABASE_URL` in Render.
   - Example: `mysql+pymysql://username:password@host:port/database`
3. Railway automatically creates the database and credentials.
4. If your app needs an initial schema, the app already runs `SchemaMigrator` and `DatabaseSeeder` at startup when `VERCEL` is not set. For Render, this will run automatically as long as the app starts with `app.py`.

---

## 4. Required environment variables

At minimum, configure:

- `FLASK_ENV=production`
- `SECRET_KEY=<strong-secret>`
- `DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:<port>/<database>`
- `CORS_ORIGINS=https://<your-render-service>.onrender.com`

Optional:
- `LOG_LEVEL=INFO`
- `UPLOAD_FOLDER=/tmp/uploads` (or Render disk path)
- `RATELIMIT_STORAGE_URL=memory://`

---

## 5. Render-specific notes

- `SESSION_COOKIE_SECURE` is enabled in production by default. Render terminates TLS at the load balancer, so the app still receives HTTP traffic internally. This is fine.
- Because the app uses Socket.IO, `gunicorn -k eventlet` is recommended.
- If you use the Render private network and Railway provides an internal host, use that host in `DATABASE_URL`.
- A `render.yaml` manifest is included in this repo for Render service configuration.

---

## 6. Deploy checklist

- [ ] Render service created
- [ ] Railway MySQL database created
- [ ] `DATABASE_URL` set on Render
- [ ] `SECRET_KEY` set on Render
- [ ] `CORS_ORIGINS` set for your Render URL
- [ ] `Procfile` committed in repo
- [ ] Build succeeded on Render
- [ ] App loads successfully on Render URL

---

## 7. Local test for Render-style production

```bash
set FLASK_ENV=production
set SECRET_KEY=supersecret123
set DATABASE_URL=mysql+pymysql://root:@localhost/ideahub_pos
python app.py
```

If the app starts, it should migrate and seed the DB automatically.
