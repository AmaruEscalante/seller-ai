import { env } from "node:process";

export const tunnelUrl = env.TUNNEL_DOMAIN.replace(/^https?:\/\//, "");

export const port = env.PORT || "3000";

export const langflowBaseUrl = env.LANGFLOW_URL;
export const langflowApiKey = env.LANGFLOW_API_KEY;
export const langflowFlowId = env.LANGFLOW_FLOW_ID;

console.log({
  langflowBaseUrl,
  langflowApiKey,
  langflowFlowId,
});
