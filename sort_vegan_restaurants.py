import re
import json
import os

# --- Configuration ---
# Set the name of your ParseHub output JSON file.
# By default, this script expects the file to be in the same directory where you run the script.
input_file_name = 'results.json' # Assuming your file is named results.json based on your output
output_file_name = 'parsed_restaurants_paris.json'
# -------------------

parsed_restaurants = []

try:
    # Construct the full path for the input file in the current working directory
    current_working_directory = os.getcwd()
    input_file_path = os.path.join(current_working_directory, input_file_name)

    print(f"Attempting to load data from: {input_file_path}")

    # Load the JSON data from the specified input file path
    with open(input_file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Ensure the 'selection1' key exists and is a list
    if "selection1" not in data or not isinstance(data["selection1"], list):
        print(f"Error: Input JSON does not contain a 'selection1' list as expected.")
    else:
        total_items = len(data["selection1"])
        print(f"Found {total_items} restaurant entries to process.")

        for i, item in enumerate(data["selection1"]):
            # Print progress as a percentage and current item index
            progress_percentage = ((i + 1) / total_items) * 100
            # Print every item's progress for detailed debugging
            print(f"Processing: {progress_percentage:.2f}% ({i + 1}/{total_items} items processed)", end='\r') 
            # Use '\r' to overwrite the line for cleaner output, remove if you want a new line per item

            try: # <--- Added try-except block for individual item processing
                # Check if 'name' key exists in the item
                if "name" not in item:
                    print(f"\nWarning: Item {i+1} missing 'name' key, skipping: {item}")
                    continue

                # Split the entire text block into individual lines, removing any empty lines
                lines = [line.strip() for line in item["name"].split('\n') if line.strip()]
                
                # Initialize a dictionary for the current restaurant's data
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
                    "address": None
                }
                
                # --- Step 1: Parse known top elements (assuming fixed order for the first few lines) ---
                
                # Restaurant Name (first line)
                if len(lines) >= 1:
                    restaurant_data["restaurant_name"] = lines[0]
                    
                # Rating and Number of Reviews (second line)
                if len(lines) >= 2:
                    rating_reviews_match = re.match(r'(\d+\.\d+)\s+\((\d+)\)', lines[1])
                    if rating_reviews_match:
                        restaurant_data["rating"] = float(rating_reviews_match.group(1))
                        restaurant_data["num_reviews"] = int(rating_reviews_match.group(2))
                    
                # Establishment Type (third line, e.g., "Vegan Restaurant")
                if len(lines) >= 3:
                    restaurant_data["establishment_type"] = lines[2]
                    
                # --- Step 2: Parse known bottom elements (phone, address, "Read Reviews") ---
                
                # Find the index of "Read Reviews" to anchor the bottom parsing
                read_reviews_idx = -1
                for i_line, line in enumerate(lines): # Renamed loop variable to avoid conflict with outer 'i'
                    if "Read Reviews" in line:
                        read_reviews_idx = i_line
                        break
                        
                if read_reviews_idx != -1:
                    # Address is always the line directly before "Read Reviews"
                    if read_reviews_idx - 1 >= 0:
                        restaurant_data["address"] = lines[read_reviews_idx - 1]
                    
                    # Phone number is the line directly before the address, if it matches the phone pattern
                    if read_reviews_idx - 2 >= 0:
                        potential_phone = lines[read_reviews_idx - 2]
                        # Use regex to confirm it's a phone number (e.g., +XX-XXXXXXXXXX)
                        if re.match(r'\+\d{1,3}-\d+', potential_phone):
                            restaurant_data["phone_number"] = potential_phone
                
                # --- Step 3: Parse the flexible middle content block ---
                
                # Determine the start and end indices of the middle content block
                # It starts after the establishment_type (index 2)
                start_content_idx = 3 
                
                # It ends before the phone number or address line, whichever comes first from the bottom
                end_content_idx = read_reviews_idx # Initialize to the "Read Reviews" line
                if restaurant_data["phone_number"]:
                    end_content_idx -= 1 # Exclude phone line
                if restaurant_data["address"]:
                    end_content_idx -= 1 # Exclude address line
                
                # Ensure the indices are valid before slicing
                if start_content_idx < end_content_idx:
                    middle_content_lines = lines[start_content_idx:end_content_idx]
                    
                    current_middle_idx = 0
                    
                    # Check for Status ("Closed" or "Open Now")
                    if current_middle_idx < len(middle_content_lines) and \
                       (middle_content_lines[current_middle_idx] == "Closed" or \
                        middle_content_lines[current_middle_idx] == "Open Now"):
                        restaurant_data["status"] = middle_content_lines[current_middle_idx]
                        current_middle_idx += 1
                        
                    # Check for Partner status ("Partner")
                    if current_middle_idx < len(middle_content_lines) and \
                       middle_content_lines[current_middle_idx] == "Partner":
                        restaurant_data["is_partner"] = True
                        current_middle_idx += 1
                        
                    # The remaining lines in the middle block form the cuisines/features and description
                    remaining_content_block_text = " ".join(middle_content_lines[current_middle_idx:]).strip()
                    
                    # Heuristic to split cuisines/features from description:
                    # Cuisines are typically comma-separated words/phrases.
                    # The description often starts with a capitalized word immediately following the last cuisine.
                    cuisines_desc_split_match = re.match(
                        r"((?:[A-Za-z0-9\-\/ ]+(?:,\s*)?)+?)\s*([A-Z].*)",
                        remaining_content_block_text,
                        re.DOTALL # Allows '.' to match newlines if description spans multiple lines (though ' '.join reduces this)
                    )
                    
                    if cuisines_desc_split_match:
                        cuisines_raw = cuisines_desc_split_match.group(1).strip()
                        # Split by comma and filter out any empty strings from splitting
                        restaurant_data["cuisines_features"] = [c.strip() for c in cuisines_raw.split(',') if c.strip()]
                        restaurant_data["description"] = cuisines_desc_split_match.group(2).strip()
                    else:
                        # Fallback if the clear split pattern (cuisines then capitalized word) is not found:
                        # If it contains commas and doesn't seem to start a sentence, assume it's all cuisines.
                        if ',' in remaining_content_block_text and not re.search(r'[.!?]\s+[A-Z]', remaining_content_block_text):
                             restaurant_data["cuisines_features"] = [c.strip() for c in remaining_content_block_text.split(',') if c.strip()]
                             restaurant_data["description"] = None # No distinct description found
                        else:
                            # Otherwise, assume the entire remaining block is the description
                            restaurant_data["description"] = remaining_content_block_text
                            restaurant_data["cuisines_features"] = [] # Ensure it's empty if no distinct cuisines
                
                # Add the parsed restaurant data to our list
                parsed_restaurants.append(restaurant_data)

            except Exception as item_e:
                print(f"\nError processing item {i+1}: {item_e}")
                print(f"Problematic item content (first 500 chars): {item.get('name', '')[:500]}...")
                # Optionally, you could save problematic items to a separate log file for later review
                continue # Continue to the next item even if this one fails

    # Convert the list of parsed restaurant dictionaries to a JSON string
    output_json = json.dumps(parsed_restaurants, indent=2, ensure_ascii=False)

    # Define the output file path in the current working directory
    output_file_path = os.path.join(current_working_directory, output_file_name)

    # Save the processed JSON to a file in the current working directory
    with open(output_file_path, 'w', encoding='utf-8') as f:
        f.write(output_json)
    
    # Print a final newline to ensure the last progress update isn't overwritten
    print("\n") 
    print(f"Successfully parsed data and saved to: {output_file_path}")

except FileNotFoundError:
    print(f"Error: Input file not found at '{input_file_path}'. Please ensure the file '{input_file_name}' is in the same directory as the script, or provide its full path.")
except json.JSONDecodeError:
    print(f"Error: Could not decode JSON from '{input_file_path}'. Please ensure it's a valid JSON file.")
except KeyboardInterrupt:
    print("\nScript interrupted by user (KeyboardInterrupt).")
    print(f"Partial data (if any) was not saved. Please run the script again without interruption.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")

