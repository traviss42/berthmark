# Multi-stage Dockerfile for Berthmark React Vite Frontend

# Stage 1: Build production bundle
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies
COPY package.json package-lock.json ./
RUN npm ci

# Copy frontend source and build configuration
COPY index.html ./
COPY tsconfig.json tsconfig.app.json tsconfig.node.json vite.config.ts tailwind.config.js postcss.config.js ./
COPY public/ ./public/
COPY src/ ./src/

# Compile static distribution bundle
RUN npm run build

# Stage 2: Serve static production assets via Nginx
FROM nginx:alpine

# Remove default nginx welcome site
RUN rm -rf /usr/share/nginx/html/*

# Copy compiled static assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy customized Nginx reverse proxy configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose HTTP port
EXPOSE 80

# Health check
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:80/ || exit 1

# Start Nginx server
CMD ["nginx", "-g", "daemon off;"]
