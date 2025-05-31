# app.py
import os
import logging
import html
import requests
import json
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response as FastAPIResponse
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI()

# --- Configuration ---
LANGFLOW_API_URL = os.getenv(
    "LANGFLOW_API_URL",
    "https://api.langflow.astra.datastax.com/lf/ae8ca9a9-1a2f-46f7-9505-71efa70416d9/api/v1/run/0ec4c098-6de6-4fe2-a92d-9050b89132a9",
)
APPLICATION_TOKEN = os.getenv("APPLICATION_TOKEN")
LANGFLOW_STREAMING = os.getenv("LANGFLOW_STREAMING", "false").lower() == "true"

# --- TwiML Constants ---
TWIML_GATHER_SPEECH_TIMEOUT_MESSAGE = (
    "I didn't catch that. Could you please say it again?"
)
TWIML_GENERIC_ERROR_MESSAGE = "I'm sorry, I encountered an issue and can't respond right now. Please try again later."
TWIML_CONFIG_ERROR_MESSAGE = "Server configuration error. The application token is missing. Unable to process your call."
TWIML_INITIAL_GREETING = "Hello! How can I assist you today?"
SPEECH_RECOGNITION_HINTS = (
    "sell car, make appointment, check order status, customer service"
)

# --- Message Constants (for WebSocket communication) ---
WS_GENERIC_ERROR_MESSAGE = "I'm sorry, I encountered an issue and can't respond right now. Please try again later."
WS_CONFIG_ERROR_MESSAGE = "Server configuration error. The application token is missing. Unable to process your call."
WS_INITIAL_GREETING = "Hello! How can I assist you today?"


# --- Helper function to parse Langflow's potentially complex JSON response ---
def parse_langflow_response(response_data: dict) -> str | None:
    """
    Attempts to extract a meaningful text response from various Langflow JSON structures.
    """
    if isinstance(response_data.get("output"), str):
        return response_data["output"]
    if isinstance(response_data.get("message"), str):
        return response_data["message"]
    if isinstance(response_data.get("text"), str):
        return response_data["text"]
    if (
        "outputs" in response_data
        and isinstance(response_data["outputs"], list)
        and len(response_data["outputs"]) > 0
    ):
        inner = response_data["outputs"][0]
        if isinstance(inner, dict) and "outputs" in inner:
            inner_outputs = inner["outputs"]
            candidate = (
                inner_outputs.get("chat_output")
                or inner_outputs.get("text_output")
                or inner_outputs.get("result")
                or next(iter(inner_outputs.values()), None)
            )
            if isinstance(candidate, str):
                return candidate
    return None


async def get_langflow_response(speech_result: str, call_sid: str) -> str:
    """
    Gets a response from Langflow, supporting streaming if configured.
    """
    if not LANGFLOW_API_URL or not APPLICATION_TOKEN:
        logger.error(f"CallSID: {call_sid} - Langflow URL or Token not configured.")
        return WS_CONFIG_ERROR_MESSAGE

    langflow_payload = {
        "input_value": speech_result,
        "output_type": "chat",
        "input_type": "chat",
        "stream": LANGFLOW_STREAMING,
    }
    langflow_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {APPLICATION_TOKEN}",
    }

    try:
        logger.info(
            f"CallSID: {call_sid} - Sending to Langflow. Streaming: {LANGFLOW_STREAMING}"
        )
        response_from_langflow = requests.post(
            LANGFLOW_API_URL,
            json=langflow_payload,
            headers=langflow_headers,
            timeout=30,
            stream=LANGFLOW_STREAMING,
        )
        response_from_langflow.raise_for_status()

        if LANGFLOW_STREAMING:
            full_reply_message = ""
            for chunk in response_from_langflow.iter_content(chunk_size=None):
                if chunk:
                    try:
                        chunk_text = chunk.decode("utf-8")
                        if chunk_text.strip().startswith(
                            "{"
                        ) and chunk_text.strip().endswith("}"):
                            data = json.loads(chunk_text)
                            streamed_content = parse_langflow_response(data)
                            if streamed_content:
                                full_reply_message += streamed_content
                            elif "text" in data:
                                full_reply_message += data["text"]

                        else:
                            full_reply_message += chunk_text
                    except Exception as e:
                        logger.warning(
                            f"CallSID: {call_sid} - Error decoding/processing stream chunk: {e} - Chunk: {chunk[:100]}"
                        )

            if not full_reply_message:
                logger.warning(f"CallSID: {call_sid} - Streaming yielded empty result.")
                return WS_GENERIC_ERROR_MESSAGE
            logger.info(
                f"CallSID: {call_sid} - Langflow streamed reply: '{full_reply_message[:100]}...'"
            )
            return full_reply_message.strip()

        else:
            langflow_reply_message = response_from_langflow.text
            content_type = response_from_langflow.headers.get("Content-Type", "")
            if "application/json" in content_type:
                try:
                    json_data = response_from_langflow.json()
                    parsed_message = parse_langflow_response(json_data)
                    if parsed_message:
                        langflow_reply_message = parsed_message
                    else:
                        logger.warning(
                            f"CallSID: {call_sid} - Could not parse Langflow JSON response: {json_data}"
                        )
                except ValueError:
                    logger.warning(
                        f"CallSID: {call_sid} - JSON parse failed, using raw text."
                    )
            logger.info(
                f"CallSID: {call_sid} - Langflow non-streamed reply: '{langflow_reply_message[:100]}...'"
            )
            return langflow_reply_message.strip()

    except requests.exceptions.RequestException as e:
        logger.error(f"CallSID: {call_sid} - Langflow request error: {e}")
        return WS_GENERIC_ERROR_MESSAGE
    except Exception as e:
        logger.error(
            f"CallSID: {call_sid} - Unexpected error in Langflow communication: {e}",
            exc_info=True,
        )
        return WS_GENERIC_ERROR_MESSAGE


@app.websocket("/ws/voice")
async def websocket_voice_endpoint(
    websocket: WebSocket, call_sid: str = "UnknownCallSID_WS"
):
    await websocket.accept()
    logger.info(f"CallSID: {call_sid} - WebSocket connection accepted.")

    if not APPLICATION_TOKEN:
        logger.error(
            f"CallSID: {call_sid} - CRITICAL: APPLICATION_TOKEN is not set for WebSocket."
        )
        await websocket.send_text(WS_CONFIG_ERROR_MESSAGE)
        await websocket.close()
        return

    try:
        while True:
            data = await websocket.receive_text()
            logger.info(
                f"CallSID: {call_sid} - Received from Twilio WebSocket: {data[:200]}"
            )

            try:
                message_data = json.loads(data)
                speech_result = None
                if (
                    message_data.get("event") == "user_speech"
                    and "speech" in message_data
                ):
                    speech_result = message_data["speech"].get("transcript")
                elif "transcript" in message_data:
                    speech_result = message_data["transcript"]
                elif isinstance(message_data, dict) and message_data.get("input_value"):
                    speech_result = message_data.get("input_value")

                current_call_sid = message_data.get("callSid", call_sid)

                if not speech_result or not speech_result.strip():
                    logger.info(
                        f"CallSID: {current_call_sid} - No valid speech in WebSocket message."
                    )
                    continue

                langflow_reply = await get_langflow_response(
                    speech_result, current_call_sid
                )

                logger.info(
                    f"CallSID: {current_call_sid} - Sending to Twilio WebSocket: {langflow_reply[:100]}..."
                )
                await websocket.send_json({"text_response": langflow_reply})

            except json.JSONDecodeError:
                logger.error(
                    f"CallSID: {call_sid} - Received non-JSON message from Twilio: {data[:200]}"
                )
                await websocket.send_text(WS_GENERIC_ERROR_MESSAGE)
            except Exception as e:
                logger.error(
                    f"CallSID: {call_sid} - Error processing WebSocket message: {e}",
                    exc_info=True,
                )
                await websocket.send_text(WS_GENERIC_ERROR_MESSAGE)

    except WebSocketDisconnect:
        logger.info(f"CallSID: {call_sid} - WebSocket disconnected.")
    except Exception as e:
        logger.error(
            f"CallSID: {call_sid} - Unexpected error in WebSocket handler: {e}",
            exc_info=True,
        )
        if websocket.client_state != websocket.client_state.DISCONNECTED:
            await websocket.close(code=1011)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
