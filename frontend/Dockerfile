FROM node:24.17.0-alpine3.24 AS build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src

RUN npm run build

FROM nginxinc/nginx-unprivileged:1.31.3-alpine3.24

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080
STOPSIGNAL SIGQUIT
