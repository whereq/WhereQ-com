# =============================================================================
# whereq.com Frontend — Production Dockerfile
# Multi-stage build: Node for build, Nginx for serving
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Build
# -----------------------------------------------------------------------------
FROM node:24.18.1-alpine AS builder

WORKDIR /app

# Copy root package.json and lock for workspace resolution
COPY package.json yarn.lock ./
COPY frontend/package.json frontend/

# Install dependencies
RUN yarn install --frozen-lockfile

# Copy frontend source
COPY frontend/ frontend/

# Build args baked into the JS bundle at build time
ARG VITE_GOOGLE_MAPS_API_KEY=""
ARG VITE_GOOGLE_MAPS_MAP_ID=""
ARG VITE_API_URL="/api"
ARG VITE_KEYCLOAK_URL=""
ARG VITE_KEYCLOAK_REALM="whereq"
ARG VITE_KEYCLOAK_CLIENT_ID="whereq-spa"

ENV VITE_GOOGLE_MAPS_API_KEY=$VITE_GOOGLE_MAPS_API_KEY
ENV VITE_GOOGLE_MAPS_MAP_ID=$VITE_GOOGLE_MAPS_MAP_ID
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_KEYCLOAK_URL=$VITE_KEYCLOAK_URL
ENV VITE_KEYCLOAK_REALM=$VITE_KEYCLOAK_REALM
ENV VITE_KEYCLOAK_CLIENT_ID=$VITE_KEYCLOAK_CLIENT_ID

# `yarn build` runs the typecheck first (tsc -p tsconfig.app.json) and only
# then bundles. Running `vite build` directly would skip it — the image must
# never ship a bundle the compiler rejected.
RUN cd frontend && yarn build

# -----------------------------------------------------------------------------
# Stage 2: Production server
# -----------------------------------------------------------------------------
FROM nginx:1.29-alpine AS runtime

LABEL maintainer="whereq Team"
LABEL description="whereq.com Frontend"

COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/frontend/dist /usr/share/nginx/html

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD wget -q --spider http://localhost:80/health || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
