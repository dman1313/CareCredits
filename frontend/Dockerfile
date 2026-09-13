# Use Node.js 20 image (Next.js 14+ prefereert Node 18/20)
FROM node:20-alpine

# Set environment variables
ENV NODE_ENV=development

# Set work directory
WORKDIR /app

# Install pnpm globally
RUN npm install -g pnpm

# Copy package files
COPY package.json pnpm-lock.yaml ./

# FIX: Allow build scripts to run (nodig voor esbuild, sharp, etc.)
RUN pnpm config set ignore-scripts false

# Install dependencies
RUN pnpm install

# Copy project files
COPY . .

# Expose port
EXPOSE 3000

# Run the application
CMD ["pnpm", "run", "dev"]