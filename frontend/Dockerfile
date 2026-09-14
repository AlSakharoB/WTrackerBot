ARG NODE_IMAGE=node:22.23.2-alpine3.23
ARG CADDY_IMAGE=caddy:2.11.4-alpine

FROM ${NODE_IMAGE} AS dependencies

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci


FROM dependencies AS quality

COPY . .

RUN npm run lint \
    && npm run typecheck \
    && npm test


FROM quality AS build

RUN npm run build \
    && npm run verify:build


FROM ${CADDY_IMAGE} AS runtime

COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
