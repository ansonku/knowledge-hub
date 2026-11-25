FROM node:24-alpine AS frontend
WORKDIR /app
COPY frontend/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY frontend/ .
RUN npm run build

FROM nginx:stable-alpine
# Videos are group-readable by "media", which the backend user also belongs to (backend/Dockerfile).
RUN addgroup -S -g 2101 media && addgroup nginx media
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend /app/dist /usr/share/nginx/html
