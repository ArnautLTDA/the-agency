import { Request, Response, NextFunction } from "express";
import { config } from "./config.js";

const EXEMPT_PATHS = new Set([
  "/health",
  "/api/v1/health",
  "/api/v1/session/status",
  "/api/v1/session/qr",
]);

export function agencyKeyMiddleware(
  req: Request,
  res: Response,
  next: NextFunction,
): void {
  const path = req.path.replace(/\/+$/, "") || "/";
  if (EXEMPT_PATHS.has(path)) {
    return next();
  }

  const providedKey = req.header("X-Agency-Key");
  if (!providedKey || providedKey !== config.agencySecretKey) {
    res.status(401).json({ error: "missing_or_invalid_agency_key" });
    return;
  }

  next();
}
