# TCFSermonSearcher

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

3. **Build the Docker Image**

   ```sh
   docker build -t tcfs-sermon-searcher .
   ```

4. **Prepare Your Audio Files**

   - Ensure your audio files are named exactly as they appear in the `sermons.db` database.
   - Place all the audio files into a directory on your host machine, for example, `/path/to/your/audiofiles`.

5. **Run the Application in a Docker Container with Mounted Audio Files**

   ```sh
   docker run -d -p 5000:5000 \
     -v /path/to/your/audiofiles:/app/audiofiles \
     --name tcfs-sermon-searcher \
     tcfs-sermon-searcher
   ```

   In this command:

   - `-v /path/to/your/audiofiles:/app/audiofiles` mounts your host machine's audio files directory to the container's `/app/audiofiles` directory. Replace `/path/to/your/audiofiles` with the actual path to your audio files on your host machine.

6. **Access the Application**

   - Open your browser and go to: `http://localhost:5000`

## Development

### Testing

Tests are written using pytest. To run the tests:

1. **Install the required packages:**

   ```sh
   pip install -r requirements.txt
   ```

2. **Run the tests:**

   ```sh
   pytest -xvs test_app.py
   ```

This will run the tests for the Flask application, checking configuration, template filters, and more.
