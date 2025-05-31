import Fastify from "fastify";
import fastifyWs from "@fastify/websocket";
import fastifyFormbody from "@fastify/formbody";
import twilio from "twilio";
import fetch from "node-fetch";

import {
  tunnelUrl,
  port,
  langflowBaseUrl,
  langflowApiKey,
  langflowFlowId,
} from "./config.js";
import { sendResponse, sendErrorAndEnd } from "./relay_responses.js";

const {
  twiml: { VoiceResponse },
} = twilio;

const fastify = Fastify({
  logger: true,
});
fastify.register(fastifyWs);
fastify.register(fastifyFormbody);

fastify.post("/voice", (_request, reply) => {
  const twiml = new VoiceResponse();
  const connect = twiml.connect();
  connect.conversationRelay({
    url: `wss://${tunnelUrl}/ws`,
    welcomeGreeting: "Ahoy! How can I help?",
  });
  reply.type("text/xml").send(twiml.toString());
});

fastify.register(async function (fastifyInstance) {
  fastifyInstance.get("/ws", { websocket: true }, (socket, request) => {
    socket.on("message", async (data) => {
      const message = JSON.parse(data);

      switch (message.type) {
        case "setup":
          fastifyInstance.log.info(`Conversation started: ${message.callSid}`);
          socket.callSid = message.callSid;
          break;
        case "prompt": {
          fastifyInstance.log.info(`Processing prompt: ${message.voicePrompt}`);
          const apiUrl = `https://api.langflow.astra.datastax.com/lf/ae8ca9a9-1a2f-46f7-9505-71efa70416d9/api/v1/run/${langflowFlowId}?stream=false`;
          const headers = {
            "Content-Type": "application/json",
            Authorization: `Bearer ${langflowApiKey}`,
          };
          const body = JSON.stringify({
            input_value: message.voicePrompt,
            output_type: "chat",
            input_type: "chat",
            session_id: socket.callSid,
          });

          try {
            const fetchResponse = await fetch(apiUrl, {
              method: "POST",
              headers: headers,
              body: body,
            });

            if (!fetchResponse.ok) {
              const errorBody = await fetchResponse.text();
              fastifyInstance.log.error(
                `Langflow API error: ${fetchResponse.status} ${fetchResponse.statusText} - ${errorBody}`
              );
              sendErrorAndEnd(
                socket,
                "I'm sorry, an application error has occurred with the Langflow API."
              );
              return;
            }

            const responseData = await fetchResponse.json();
            const outputText =
              responseData.outputs[0].outputs[0].results.message.text;
            sendResponse(socket, outputText);
            fastifyInstance.log.info(`Response: ${outputText}`);
          } catch (error) {
            fastifyInstance.log.error(
              `Error processing prompt or calling Langflow: ${error.message}`
            );
            sendErrorAndEnd(
              socket,
              "I'm sorry, an application error has occurred."
            );
          }
          break;
        }
        case "error":
          fastifyInstance.log.error(
            `ConversationRelay error: ${message.description}`
          );
          break;
        default:
          fastifyInstance.log.error("Unknown message type:", message);
      }
    });

    socket.on("close", async () => {
      fastifyInstance.log.info(
        `WebSocket connection closed: ${socket.callSid}`
      );
    });
  });
});

try {
  await fastify.listen({ port });
} catch (err) {
  fastify.log.error(err);
  process.exit(1);
}
