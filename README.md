
# NGA Highlights Scraper

This project is a web scraper designed to extract information about artworks from the National Gallery of Art website, specifically from the "Highlights" section. It uses Selenium for browser automation, BeautifulSoup for HTML parsing, and the requests library for downloading images.

## Features

- **Artwork Data Scraping:** Extracts detailed information about artworks, including:
  - **Title**: The name of the artwork.
  - **Artist**: The name of the creator(s) of the artwork.
  - **Date**: The date or time period when the artwork was created.
  - **Technique**: The materials and methods used in creating the artwork.
  - **Dimensions**: The physical size or scale of the artwork.
  - **Provenance**: The history of ownership of the artwork.
  - **Exhibition History**: Details of where the artwork has been displayed.
  - **Bibliography**: References to the artwork in publications or literature.
  - **Related Content**: Additional resources or links related to the artwork.
  - **Description**: A detailed narrative about the artwork, its significance, or context.
  - **Accession Number**: The unique identifier assigned by the museum or gallery.
  - **Location**: The current display location of the artwork within the gallery.
  - **Image URL**: The URL or file path of the artwork's image.
- **Dynamic Content Handling:** Clicks buttons to reveal hidden tabs and extracts information from dynamically loaded content.
- **Image Downloading:** Downloads images of artworks and saves them to a specified folder.
- **Interruptible Execution:** Supports graceful interruption of the scraping process using Ctrl+C.
- **Logging:** Provides detailed logging of the scraping process, including errors and warnings.
- **JSON Output:** Saves collected data in a structured JSON format.
- **Dockerized:** Includes a Dockerfile and docker-compose.yml for easy deployment and running in a containerized environment.

## Requirements

- Python 3.9
- Chrome browser
- ChromeDriver
- Required Python packages (listed in the `requirements.txt` file)

## Installation

1. **Clone the repository:**

   ```bash
   git clone <repository_address>
   cd <repository_directory>
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Set up ChromeDriver:**

   - Download the appropriate version of ChromeDriver for your Chrome browser from [the official website](https://chromedriver.chromium.org/downloads).
   - Ensure the ChromeDriver executable is in your system's PATH.

## Usage

### Running the Scraper

Run the script:

```bash
python Alexa_v2.py run
```

### Interrupting the Scraper

To interrupt the scraper, use the Ctrl+C keyboard shortcut. The process will gracefully stop, and all collected data will be saved.

## Output

The output data is saved in JSON format in a specified output folder. Artwork images are downloaded and saved in a folder named `images` within the project directory.

## Docker

### Building the Image

To build the Docker image, use the following command:

```bash
docker build -t nga_highlights_scraper .
```

### Running the Container

Run the scraper in a Docker container:

```bash
docker-compose up
```