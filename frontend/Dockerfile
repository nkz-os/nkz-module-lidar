# Multi-stage build for LIDAR Module Frontend
# NOTE: In production, Nekazari serves module bundles from MinIO (IIFE runtime script injection).
# This container is optional and mainly useful for local/testing deployments.
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files from root
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm install --registry=https://registry.npmjs.org/

# Copy all source files needed for build
COPY src/ ./src/
COPY index.html ./
COPY vite.config.ts ./
COPY tsconfig.json ./
COPY tsconfig.node.json ./
COPY tailwind.config.js ./
COPY postcss.config.js ./
COPY manifest.json ./

# Build the application
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

# Copy built assets (IIFE bundle: nkz-module.js)
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx config
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Health endpoint
RUN echo "OK" > /usr/share/nginx/html/health

# Expose port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

