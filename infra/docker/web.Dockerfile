# Imagem do painel: build do apps/web servido pelo Caddy. Build pela raiz do repositório:
#   docker build -f infra/docker/web.Dockerfile .
FROM node:24.21.0-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS build

WORKDIR /app

# Dependências primeiro, para reaproveitar a camada quando só o código muda.
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web/index.html apps/web/tsconfig.json apps/web/vite.config.ts ./
COPY apps/web/src ./src
RUN npm run build

FROM caddy:2.11.4-alpine@sha256:6aeddd44c3078b0f9a35206472a11420648a79c184603ef95957d0a20044cb2b

COPY infra/compose/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
