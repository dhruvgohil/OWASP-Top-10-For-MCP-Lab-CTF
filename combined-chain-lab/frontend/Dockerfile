FROM node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .
RUN npm run build

EXPOSE 3000

# Serve the production build. VITE_API_BASE is baked at build time (defaults to
# http://localhost:8000, which is where the browser reaches the backend on the host).
CMD ["npm", "run", "preview"]
