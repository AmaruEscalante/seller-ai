from fastapi import FastAPI
from pydantic import BaseModel
import asyncio
import os
from dotenv import load_dotenv
from typing import List, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from browser_use import Agent, Browser, BrowserProfile

load_dotenv()

app = FastAPI()

# Define the example payload for testing
EXAMPLE_CAR_PAYLOAD = {
    "listing_title": "Example Vehicle for Sale",
    "photos": [
        "https://example.com/photo1.jpg",  # Placeholder, actual image URLs or accessible paths needed for agent
        "https://example.com/photo2.jpg",
    ],
    "video_url": "https://example.com/video.mp4",
    "vehicle_type": "Car",
    "year": 2016,
    "make": "Toyota",
    "model": "Corolla",
    "number_of_owners": 2,
    "location_zip_code": "11102",
    "price": {"amount": 15000, "currency": "USD"},
    "description": "Well-maintained red 2016 Toyota Corolla. Minor scratch on the rear bumper. No accident history. Standard warranty still active until [Date]. Clean title.",
    "lister_name": "Christian Chavez",
}


class PriceInfo(BaseModel):
    amount: float
    currency: str


class CarDetails(BaseModel):
    listing_title: str
    photos: List[str]
    video_url: Optional[str] = None
    vehicle_type: str
    year: int
    make: str
    model: str
    number_of_owners: Optional[int] = None
    location_zip_code: str
    price: PriceInfo
    description: str
    lister_name: str


# Configure the browser agent
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash-exp", api_key=os.getenv("GEMINI_API_KEY")
)

browser_config = BrowserProfile(
    headless=False,  # Set to True if you don't want to see the browser UI
    # If you have a specific Chromium/Chrome binary, specify its path here.
    # For example, on Linux: executable_path="/usr/bin/chromium-browser"
    # For example, on MacOS: executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    user_data_dir=None,  # Consider setting a user_data_dir if you want to persist logins/cookies
)


async def post_car_to_facebook(car: CarDetails):
    """Triggers the browser agent to post the car listing on Facebook Marketplace."""
    # This prompt needs significant refinement for a real-world scenario.
    # It should guide the LLM step-by-step through the Facebook Marketplace UI.
    # Handling logins, multi-page forms, and potential errors is crucial.

    # Constructing the photo part of the prompt.
    # The agent will need to handle multiple photos. The exact phrasing here will depend on how the LLM interprets "upload photos".
    # It might need to be told to upload them one by one or look for a multi-file upload.
    # For now, we list them. Actual image paths accessible to the browser will be needed.
    # The example URLs are placeholders and won't work for actual upload.
    # You'll need to replace them with accessible URLs or local file paths (and ensure browser_use can handle local paths for uploads).
    # If using local paths, ensure they are absolute or relative to where the browser process can access them.
    # For your specific image: "/Users/amaru-mac/Documents/hackathons/hacking-agents/2016-toyota-corolla-4-door-sedan-cvt-le-gs-angular-front-exterior-view_100524572_m.jpg"
    # We will use the first photo from the payload for this example, but the prompt needs to be robust for multiple.

    photo_instructions = "Upload the following photos: " + ", ".join(car.photos)
    if not car.photos:
        photo_instructions = "No photos provided for upload."
    elif len(car.photos) == 1 and car.photos[0].startswith(
        "https://example.com"
    ):  # if using placeholder from test
        # Use the user's specific local image if the test payload's default photos are present
        local_image_path = "/Users/amaru-mac/Documents/hackathons/hacking-agents/2016-toyota-corolla-4-door-sedan-cvt-le-gs-angular-front-exterior-view_100524572_m.jpg"
        if os.path.exists(local_image_path):
            photo_instructions = f"Upload the photo from the path: {local_image_path}"
        else:
            photo_instructions = "Specified local photo not found, and example.com photos are placeholders."

    prompt = f"""
    1. Go to Facebook and ensure you are logged in. If not, log in first.
    2. Navigate to Facebook Marketplace.
    3. Click on 'Create new listing'.
    4. Select 'Item for Sale', then choose the 'Vehicles' category.
    5. Fill in the vehicle listing form with the following details:
        - Listing Title: {car.listing_title}
        - Vehicle Type: {car.vehicle_type} (e.g., Car/Truck)
        - Year: {car.year}
        - Make: {car.make}
        - Model: {car.model}
        - Price: {car.price.amount} {car.price.currency}
        - Description: {car.description}
        - Location (Zip Code): {car.location_zip_code}
        - Number of Owners: {car.number_of_owners if car.number_of_owners is not None else 'Not specified'}
    6. {photo_instructions}
    7. If there's an option to add a video and a video URL is provided ({car.video_url}), add it.
    8. Fill in your name as the lister if prompted: {car.lister_name}.
    9. Review all details carefully.
    10. Publish the listing.
    """
    print(f"Attempting to post car with title: {car.listing_title}")
    print(f"Using prompt:\\n{prompt}")

    # It's good practice to launch a new browser session per task for isolation
    browser = Browser(browser_profile=browser_config)
    try:
        context = await browser.new_context()
        # Consider increasing max_steps if the Facebook posting process is long
        agent = Agent(
            browser_context=context,
            task=prompt,
            llm=llm,
            max_steps=50,  # Increased max_steps
        )
        result = await agent.run()
        print(f"Agent finished with result: {result}")
        return {
            "status": "success",
            "agent_result": str(result),
        }  # Ensure result is serializable
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback

        traceback.print_exc()
        return {"status": "error", "message": str(e)}
    finally:
        await browser.close()


@app.post("/post_car_listing/")
async def create_car_listing(car: CarDetails):
    """
    API endpoint to receive car details and trigger the Facebook Marketplace posting.
    """
    result = await post_car_to_facebook(car)
    return result


@app.post("/test_post_car_listing/")
async def test_create_car_listing():
    """
    API endpoint to trigger a test car listing using the predefined example payload.
    Call this endpoint when you run the server with your --test flag/scenario.
    """
    print("Received request to /test_post_car_listing/")
    car_data_to_post = EXAMPLE_CAR_PAYLOAD.copy()

    # Update photos to use the user's specified image for the test payload
    # This makes the test payload actually attempt to upload the user's image.
    user_specific_image = "/Users/amaru-mac/Documents/hackathons/hacking-agents/2016-toyota-corolla-4-door-sedan-cvt-le-gs-angular-front-exterior-view_100524572_m.jpg"
    if os.path.exists(user_specific_image):
        car_data_to_post["photos"] = [user_specific_image]
    else:
        print(
            f"Warning: Test image {user_specific_image} not found. Using placeholder URLs which will likely fail for upload."
        )

    car_details_model = CarDetails(**car_data_to_post)
    result = await post_car_to_facebook(car_details_model)
    return result


@app.get("/")
async def root():
    return {
        "message": "Car Listing Agent API is running. Use POST /post_car_listing/ or POST /test_post_car_listing/."
    }


# To run this server: uvicorn agent.server:app --reload
# Then you can send a POST request to /post_car_listing/ with car details,
# OR send a POST request to /test_post_car_listing/ to use the example payload.
# Example using curl for the test endpoint:
# curl -X POST "http://127.0.0.1:8000/test_post_car_listing/"
#
# Example for the main endpoint:
# curl -X POST "http://127.0.0.1:8000/post_car_listing/" -H "Content-Type: application/json" -d '{
#   "listing_title": "My Awesome Toyota Corolla",
#   "photos": ["/path/to/your/photo1.jpg", "/path/to/your/photo2.jpg"],
#   "video_url": "https://www.youtube.com/watch?v=yourvideo",
#   "vehicle_type": "Car",
#   "year": 2016,
#   "make": "Toyota",
#   "model": "Corolla",
#   "number_of_owners": 1,
#   "location_zip_code": "90210",
#   "price": {"amount": 14500, "currency": "USD"},
#   "description": "Excellent condition 2016 Toyota Corolla. Low mileage, very clean.",
#   "lister_name": "Jane Doe"
# }'
