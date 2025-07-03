import re
import json
import os
from datetime import datetime

# --- Configuration ---
input_file_name = 'results.json'
output_file_name = 'parsed_restaurants_paris.json'
error_log_file = 'parsing_errors.log'
# -------------------

def log_error(message, item=None):
    """Log errors to a file with timestamp for debugging."""
    with open(error_log_file, 'a', encoding='utf-8') as f:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        f.write(f"[{timestamp}] {message}\n")
        if item:
            f.write(f"Item content: {json.dumps(item, ensure_ascii=False)[:500]}...\n")
        f.write("-" * 80 + "\n")

def parse_restaurant_item(item, index, total_items):
    """Parse a single restaurant item and return structured data."""
    restaurant_data = {
        "restaurant_name": None,
        "rating": None,
        "num_reviews": None,
        "establishment_type": None,
        "status": None,
        "is_partner": False,
        "cuisines_features": [],
        "description": None,
        "phone_number": None,
        "address": None,
        "reviews": []  # New: List to store reviews
    }

    try:
        # Check if 'name' key exists
        if "name" not in item:
            log_error(f"Item {index+1} missing 'name' key, skipping.", item)
            return None

        # Split text into lines, removing empty ones
        lines = [line.strip() for line in item["name"].split('\n') if line.strip()]
        if not lines:
            log_error(f"Item {index+1} has empty 'name' content, skipping.", item)
            return None

        # --- Step 1: Parse top elements ---
        if len(lines) >= 1:
            restaurant_data["restaurant_name"] = lines[0]
        
        if len(lines) >= 2:
            rating_reviews_match = re.match(r'(\d+\.\d+)\s+\((\d+)\)', lines[1])
            if rating_reviews_match:
                restaurant_data["rating"] = float(rating_reviews_match.group(1))
                restaurant_data["num_reviews"] = int(rating_reviews_match.group(2))
            else:
                log_error(f"Item {index+1}: Failed to parse rating/reviews from '{lines[1]}'.")

        if len(lines) >= 3:
            restaurant_data["establishment_type"] = lines[2]

        # --- Step 2: Parse bottom elements (phone, address, reviews) ---
        read_reviews_idx = -1
        for i_line, line in enumerate(lines):
            if "Read Reviews" in line:
                read_reviews_idx = i_line
                break

        if read_reviews_idx != -1:
            if read_reviews_idx - 1 >= 0:
                restaurant_data["address"] = lines[read_reviews_idx - 1]
            
            if read_reviews_idx - 2 >= 0:
                potential_phone = lines[read_reviews_idx - 2]
                if re.match(r'\+\d{1,3}-\d+', potential_phone):
                    restaurant_data["phone_number"] = potential_phone
                else:
                    log_error(f"Item {index+1}: Invalid phone number format '{potential_phone}'.")

        # --- Step 3: Parse middle content ---
        start_content_idx = 3
        end_content_idx = read_reviews_idx if read_reviews_idx != -1 else len(lines)
        if restaurant_data["phone_number"]:
            end_content_idx -= 1
        if restaurant_data["address"]:
            end_content_idx -= 1

        if start_content_idx < end_content_idx:
            middle_content_lines = lines[start_content_idx:end_content_idx]
            current_middle_idx = 0

            # Status
            if current_middle_idx < len(middle_content_lines) and \
               middle_content_lines[current_middle_idx] in ["Closed", "Open Now"]:
                restaurant_data["status"] = middle_content_lines[current_middle_idx]
                current_middle_idx += 1

            # Partner
            if current_middle_idx < len(middle_content_lines) and \
               middle_content_lines[current_middle_idx] == "Partner":
                restaurant_data["is_partner"] = True
                current_middle_idx += 1

            # Remaining content: cuisines/features and description
            remaining_content = " ".join(middle_content_lines[current_middle_idx:]).strip()
            if remaining_content:
                cuisines_desc_match = re.match(
                    r"((?:[A-Za-z0-9\-\/ ]+(?:,\s*)?)+?)\s*([A-Z].*)?",
                    remaining_content,
                    re.DOTALL
                )
                if cuisines_desc_match:
                    cuisines_raw = cuisines_desc_match.group(1).strip()
                    restaurant_data["cuisines_features"] = [c.strip() for c in cuisines_raw.split(',') if c.strip()]
                    restaurant_data["description"] = cuisines_desc_match.group(2).strip() if cuisines_desc_match.group(2) else None
                else:
                    if ',' in remaining_content:
                        restaurant_data["cuisines_features"] = [c.strip() for c in remaining_content.split(',') if c.strip()]
                    else:
                        restaurant_data["description"] = remaining_content

        # --- Step 4: Parse reviews ---
        if "reviews" in item and item["reviews"]:
            reviews = item["reviews"]
            if isinstance(reviews, list):
                # Handle case where reviews is a list of strings or dictionaries
                for review in reviews:
                    if isinstance(review, dict):
                        # Expect keys like 'text', 'rating', 'date' (if available)
                        restaurant_data["reviews"].append({
                            "text": review.get("text", ""),
                            "rating": float(review["rating"]) if review.get("rating") else None,
                            "date": review.get("date")
                        })
                    elif isinstance(review, str):
                        # Handle plain text reviews
                        restaurant_data["reviews"].append({"text": review.strip()})
            elif isinstance(reviews, str):
                # Handle reviews as a single text block
                review_lines = [r.strip() for r in reviews.split('\n') if r.strip()]
                restaurant_data["reviews"] = [{"text": r} for r in review_lines]
        else:
            log_error(f"Item {index+1}: No reviews found or empty reviews field.")

        return restaurant_data

    except Exception as e:
        log_error(f"Item {index+1} processing failed: {str(e)}", item)
        return None

def remove_null_fields(parsed_restaurants):
    """Remove fields that are null for all items, unless at least one item has a non-null value."""
    if not parsed_restaurants:
        return parsed_restaurants

    # Get all possible fields from the first restaurant
    fields = list(parsed_restaurants[0].keys())
    fields_to_remove = []

    # Check each field
    for field in fields:
        all_null = True
        for restaurant in parsed_restaurants:
            if restaurant[field] is not None and not (
                isinstance(restaurant[field], (list, dict)) and not restaurant[field]
            ):
                all_null = False
                break
        if all_null:
            fields_to_remove.append(field)

    # Remove fields that are null for all items
    for restaurant in parsed_restaurants:
        for field in fields_to_remove:
            restaurant.pop(field, None)

    return parsed_restaurants

def main():
    parsed_restaurants = []
    current_working_directory = os.getcwd()
    input_file_path = os.path.join(current_working_directory, input_file_name)
    output_file_path = os.path.join(current_working_directory, output_file_name)

    try:
        print(f"Attempting to load data from: {input_file_path}")
        with open(input_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if "selection1" not in data or not isinstance(data["selection1"], list):
            print(f"Error: Input JSON does not contain a 'selection1' list.")
            return

        total_items = len(data["selection1"])
        if total_items == 0:
            print("Error: No restaurant entries found in 'selection1'.")
            return

        print(f"Found {total_items} restaurant entries to process.")

        for i, item in enumerate(data["selection1"]):
            if (i + 1) % max(100, total_items // 10) == 0 or i == total_items - 1:
                progress_percentage = ((i + 1) / total_items) * 100
                print(f"Processing: {progress_percentage:.2f}% ({i + 1}/{total_items} items processed)")

            restaurant_data = parse_restaurant_item(item, i, total_items)
            if restaurant_data:
                parsed_restaurants.append(restaurant_data)

        if not parsed_restaurants:
            print("Error: No valid restaurant data parsed.")
            return

        # Remove fields that are null for all items
        parsed_restaurants = remove_null_fields(parsed_restaurants)

        # Save output
        output_json = json.dumps(parsed_restaurants, indent=2, ensure_ascii=False)
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(output_json)
        
        print(f"\nSuccessfully parsed {len(parsed_restaurants)}/{total_items} restaurants and saved to: {output_file_path}")
        if len(parsed_restaurants) < total_items:
            print(f"Note: {total_items - len(parsed_restaurants)} items were skipped due to errors. Check '{error_log_file}' for details.")

    except FileNotFoundError:
        print(f"Error: Input file not found at '{input_file_path}'.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{input_file_path}'.")
    except KeyboardInterrupt:
        print("\nScript interrupted by user.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()