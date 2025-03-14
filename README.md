# TCFSermonSearcher

A Flask-based web application for searching sermon transcriptions, with AI-enhanced search capabilities and multilingual support.

## Running with Docker

The recommended way to run TCFSermonSearcher is via Docker. Follow these steps:

1. **Clone the Repository**

   ```sh
   git clone https://github.com/jaycollett/TCFSermonSearcher.git
   ```

2. **Navigate to the Project Directory**

   ```sh
   cd TCFSermonSearcher
   ```

3. **Create Required Directories**

   The application requires specific directories for storing data. Create them with:

   ```sh
   mkdir -p data audiofiles
   ```

   - The `data` directory will contain the SQLite database
   - The `audiofiles` directory will store sermon audio files

4. **Prepare Database File**

   Ensure the `data` directory contains a `sermons.db` file (even if empty). If it doesn't exist:

   ```sh
   touch data/sermons.db
   ```

   The application will automatically initialize the database schema when it starts.

5. **Build the Docker Image**

   ```sh
   docker build -t tcfs-sermon-searcher .
   ```

6. **Run the Application in a Docker Container**

   ```sh
   docker run -d -p 5000:5000 \
     -v $(pwd)/data:/app/data \
     -v $(pwd)/audiofiles:/data/audiofiles \
     --name tcfs-sermon-searcher \
     tcfs-sermon-searcher
   ```

   This command:
   - Maps port 5000 from the container to your host
   - Mounts the local `data` directory to `/app/data` in the container
   - Mounts the local `audiofiles` directory to `/data/audiofiles` in the container
   - Names the container "tcfs-sermon-searcher"

7. **Access the Application**

   Open your browser and go to: `http://localhost:5000`

## Development

### Project Structure

- `app.py` - Application factory and configuration
- `models.py` - Database models and utilities
- `routes.py` - Application routes and views
- `config/` - Configuration for different environments
- `templates/` - HTML templates
- `static/` - Static assets (CSS, JavaScript, images)
- `translations/` - Internationalization files

### Setup Development Environment

1. **Create a virtual environment**

   ```sh
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**

   ```sh
   pip install -r requirements.txt
   ```

3. **Set environment variables**

   ```sh
   export FLASK_ENV=development
   export FLASK_APP=app:create_app
   ```

4. **Run the application**

   ```sh
   flask run
   ```

### Testing

Tests are written using pytest. To run the tests:

```sh
pytest -xvs test_app.py
```

### Building and Pushing New Docker Images

To build and push a new version to Docker Hub:

```sh
docker build -t yourusername/tcfs-sermon-searcher:latest .
docker push yourusername/tcfs-sermon-searcher:latest
```
