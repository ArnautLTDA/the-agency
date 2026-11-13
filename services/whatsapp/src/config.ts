import dotenv from "dotenv";

dotenv.config();

export interface AppConfig {
  port: number;
  agencySecretKey: string;
  rabbitmqUrl: string;
  authDir: string;
  businessHoursStart: string;
  businessHoursEnd: string;
  timezone: string;
}

export const config: AppConfig = {
  port: parseInt(process.env.WHATSAPP_PORT || "3005", 10),
  agencySecretKey:
    process.env.AGENCY_SECRET_KEY || "agency_dev_secret_key_12345",
  rabbitmqUrl:
    process.env.RABBITMQ_URL || "amqp://agency:agency123@localhost:5672/",
  authDir: process.env.AUTH_DIR || "./storage/whatsapp/auth_info",
  businessHoursStart: process.env.BUSINESS_HOURS_START || "08:30",
  businessHoursEnd: process.env.BUSINESS_HOURS_END || "18:30",
  timezone: process.env.TIMEZONE || "America/Sao_Paulo",
};
