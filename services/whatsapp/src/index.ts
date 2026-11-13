import { createApp } from "./app.js";
import { config } from "./config.js";
import { WhatsAppSessionManager } from "./session.js";

const sessionManager = new WhatsAppSessionManager();
const app = createApp(sessionManager);

app.listen(config.port, () => {
  console.log(`WhatsApp Gateway Service listening on port ${config.port}`);
});
