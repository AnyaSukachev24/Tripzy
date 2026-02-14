# Amadeus API: Top 10 Essential Filter & SSR Codes

This guide provides the mapping between user requirements and the technical codes required for the Amadeus for Developers API. Use these within the `amenities` parameter for Hotels or the `remark` / `serviceRequests` fields for Flights.

---

### 1. DISABLED_FACILITIES
* **Usage:** When a user mentions **wheelchair access**, **limited mobility**, or **ADA compliance**.
* **Example:** "Find me an accessible hotel room in Berlin."

### 2. PETS_ALLOWED
* **Usage:** Essential for **pet-friendly trip** logic.
* **Example:** "I'm traveling with my dog; show me hotels that allow pets."

### 3. WIFI
* **Usage:** The primary filter for **digital nomad requirements**. 
* **Note:** Often paired with `BUSINESS_CENTER` for users who need to work.
* **Example:** "I need a place with reliable internet for Zoom calls."

### 4. KSML (Kosher Meal)
* **Usage:** For **special dietary restrictions** (Religious/Kosher).
* **Example:** "Ensure my flight to NYC includes a Kosher meal."

### 5. VGML (Vegan Meal)
* **Usage:** For **vegan/plant-based** dietary requirements.
* **Note:** Use `VLML` instead if the user is vegetarian (dairy/eggs allowed).
* **Example:** "The user is strictly vegan."

### 6. WCHR (Wheelchair - Ramp)
* **Usage:** For **accessibility needs** specifically at the airport.
* **Note:** Use this for passengers who can walk a little but need help with long distances/ramps.
* **Example:** "The traveler has trouble walking long distances through terminals."

### 7. PARKING
* **Usage:** Critical for **road-trip planning** or users renting a car.
* **Example:** "I'm driving to the hotel and need a place to park."

### 8. AIR_CONDITIONING
* **Usage:** Vital for **comfort/health** preferences, especially in tropical or European summer destinations.
* **Example:** "The user won't stay anywhere without A/C."

### 9. FITNESS_CENTER
* **Usage:** For users with **active lifestyle** preferences or "lifelong athletes."
* **Example:** "A gym is a non-negotiable for my morning routine."

### 10. RESTAURANT
* **Usage:** Use as a "parent filter" for **dietary restrictions** at hotels.
* **Note:** If a user has complex allergies or needs Kosher/Halal food, ensure the hotel has an on-site restaurant for easier meal management.
* **Example:** "I need a hotel that serves food on-site so I don't have to search for accessible dining."

### 11. BUSINESS_CENTER
* **Usage:** For **digital nomad requirements** where the user needs more than just WiFi (printers, scanning, or formal workspaces).
* **Example:** "I need to print documents and have a professional setting for a meeting."

### 12. BABYSITTING
* **Usage:** For family travelers or users requesting **childcare services**.
* **Example:** "Find a hotel that offers childcare so the parents can have dinner."

### 13. SPA
* **Usage:** For **wellness-focused** trips or high-end relaxation preferences.
* **Example:** "The user is looking for a luxury wellness retreat with a spa."

### 14. MOML (Muslim Meal)
* **Usage:** For **special dietary restrictions** (Halal).
* **Example:** "Please ensure all meals provided are Halal-certified."

### 15. GFML (Gluten Intolerant Meal)
* **Usage:** For users with **celiac disease or gluten allergies**.
* **Example:** "The traveler is gluten-intolerant; update the meal preference."

### 16. WCHC (Wheelchair - Completely Immobile)
* **Usage:** For the highest level of **accessibility needs**.
* **Note:** Unlike `WCHR`, this signals that the passenger is completely immobile and requires a chair to their seat.
* **Example:** "The user is a full-time wheelchair user and cannot climb aircraft stairs."

### 17. PETC (Pet in Cabin)
* **Usage:** Specifically for **pet-friendly trip** logic regarding the flight itself.
* **Note:** This is a request to bring a small pet inside the passenger cabin.
* **Example:** "I want to fly with my Maltipoo puppy in the cabin with me."

---

**Example Logic:**
```python
if "dog" in user_input or "pet" in user_input:
    search_params['amenities'].append('PETS_ALLOWED')