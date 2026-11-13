FROM node:20-alpine
WORKDIR /app
COPY services/whatsapp/package*.json ./
RUN npm install
COPY services/whatsapp/ .
RUN npm run build
EXPOSE 3005
CMD ["node", "dist/index.js"]
