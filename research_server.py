import arxiv
import json
import os
import subprocess
from typing import List
from mcp.server.fastmcp import FastMCP

PAPER_DIR = "papers"
FFMPEG_DIR = "/Users/trdo/Desktop"

# Initialize FastMCP server
mcp = FastMCP("research")

@mcp.tool()
def convert_video_ffmpeg(input_filename: str, output_filename: str = "") -> str:
    """
    Convert a video file using FFmpeg with high quality settings.
    
    Args:
        input_filename: Name of the input video file (e.g., "input.mov")
        output_filename: Name of the output video file (optional, defaults to input name with .mp4 extension)
        
    Returns:
        Success or error message with command output
    """
    
    # Set default output filename if not provided
    if not output_filename:
        name, _ = os.path.splitext(input_filename)
        output_filename = f"{name}.mp4"
    
    # Full paths for input and output files
    input_path = os.path.join(FFMPEG_DIR, input_filename)
    output_path = os.path.join(FFMPEG_DIR, output_filename)
    
    # Check if input file exists
    if not os.path.exists(input_path):
        return f"Error: Input file '{input_filename}' not found in {FFMPEG_DIR}"
    
    # Check if output file already exists
    if os.path.exists(output_path):
        return f"Output file '{output_filename}' already exists. Please choose a different name or remove the existing file."
    
    # Construct the ffmpeg command
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-qscale", "0",
        output_path
    ]
    
    try:
        # Start the ffmpeg process without waiting for completion
        process = subprocess.Popen(
            cmd,
            cwd=FFMPEG_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Return immediately with process started message
        return f"FFmpeg conversion started for '{input_filename}' -> '{output_filename}'\nProcess ID: {process.pid}\nCommand: {' '.join(cmd)}\n\nThe conversion is running in the background. Use check_conversion_status() to monitor progress."
        
    except FileNotFoundError:
        return "Error: FFmpeg not found. Please make sure FFmpeg is installed and available in your PATH"
    except Exception as e:
        return f"Error starting FFmpeg: {str(e)}"

@mcp.tool()
def check_conversion_status() -> str:
    """
    Check the status of any running FFmpeg processes and list completed conversions.
    
    Returns:
        Status of FFmpeg processes and recent conversions
    """
    
    try:
        # Check for running ffmpeg processes
        result = subprocess.run(
            ["pgrep", "-f", "ffmpeg"],
            capture_output=True,
            text=True
        )
        
        status_msg = "=== FFmpeg Process Status ===\n"
        
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            status_msg += f"Running FFmpeg processes: {len(pids)}\n"
            for pid in pids:
                status_msg += f"- Process ID: {pid}\n"
        else:
            status_msg += "No FFmpeg processes currently running.\n"
        
        # List recent video files in the directory
        status_msg += f"\n=== Recent files in {FFMPEG_DIR} ===\n"
        
        video_extensions = ['.mov', '.mp4', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v']
        files = []
        
        if os.path.exists(FFMPEG_DIR):
            for file in os.listdir(FFMPEG_DIR):
                if any(file.lower().endswith(ext) for ext in video_extensions):
                    file_path = os.path.join(FFMPEG_DIR, file)
                    modified_time = os.path.getmtime(file_path)
                    files.append((file, modified_time))
        
        # Sort by modification time (newest first)
        files.sort(key=lambda x: x[1], reverse=True)
        
        for file, mod_time in files[:10]:  # Show last 10 files
            file_path = os.path.join(FFMPEG_DIR, file)
            file_size = os.path.getsize(file_path)
            size_mb = file_size / (1024 * 1024)
            from datetime import datetime
            mod_date = datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M:%S")
            status_msg += f"- {file} ({size_mb:.1f} MB) - Modified: {mod_date}\n"
        
        return status_msg
        
    except Exception as e:
        return f"Error checking conversion status: {str(e)}"

@mcp.tool()
def list_video_files() -> str:
    """
    List all video files in the FFmpeg working directory.
    
    Returns:
        List of video files found in the directory
    """
    
    video_extensions = ['.mov', '.mp4', '.avi', '.mkv', '.wmv', '.flv', '.webm', '.m4v']
    
    try:
        if not os.path.exists(FFMPEG_DIR):
            return f"Error: Directory {FFMPEG_DIR} does not exist"
        
        files = os.listdir(FFMPEG_DIR)
        video_files = [f for f in files if any(f.lower().endswith(ext) for ext in video_extensions)]
        
        if video_files:
            result = f"Video files found in {FFMPEG_DIR}:\n"
            for i, file in enumerate(video_files, 1):
                file_path = os.path.join(FFMPEG_DIR, file)
                file_size = os.path.getsize(file_path)
                size_mb = file_size / (1024 * 1024)
                result += f"{i}. {file} ({size_mb:.1f} MB)\n"
            return result
        else:
            return f"No video files found in {FFMPEG_DIR}"
            
    except Exception as e:
        return f"Error listing video files: {str(e)}"
    
@mcp.tool()
def search_papers(topic: str, max_results: int = 5) -> List[str]:
    """
    Search for papers on arXiv based on a topic and store their information.
    
    Args:
        topic: The topic to search for
        max_results: Maximum number of results to retrieve (default: 5)
        
    Returns:
        List of paper IDs found in the search
    """
    
    # Use arxiv to find the papers 
    client = arxiv.Client()

    # Search for the most relevant articles matching the queried topic
    search = arxiv.Search(
        query = topic,
        max_results = max_results,
        sort_by = arxiv.SortCriterion.Relevance
    )

    papers = client.results(search)
    
    # Create directory for this topic
    path = os.path.join(PAPER_DIR, topic.lower().replace(" ", "_"))
    os.makedirs(path, exist_ok=True)
    
    file_path = os.path.join(path, "papers_info.json")

    # Try to load existing papers info
    try:
        with open(file_path, "r") as json_file:
            papers_info = json.load(json_file)
    except (FileNotFoundError, json.JSONDecodeError):
        papers_info = {}

    # Process each paper and add to papers_info  
    paper_ids = []
    for paper in papers:
        paper_ids.append(paper.get_short_id())
        paper_info = {
            'title': paper.title,
            'authors': [author.name for author in paper.authors],
            'summary': paper.summary,
            'pdf_url': paper.pdf_url,
            'published': str(paper.published.date())
        }
        papers_info[paper.get_short_id()] = paper_info
    
    # Save updated papers_info to json file
    with open(file_path, "w") as json_file:
        json.dump(papers_info, json_file, indent=2)
    
    print(f"Results are saved in: {file_path}")
    
    return paper_ids

@mcp.tool()
def extract_info(paper_id: str) -> str:
    """
    Search for information about a specific paper across all topic directories.
    
    Args:
        paper_id: The ID of the paper to look for
        
    Returns:
        JSON string with paper information if found, error message if not found
    """
 
    for item in os.listdir(PAPER_DIR):
        item_path = os.path.join(PAPER_DIR, item)
        if os.path.isdir(item_path):
            file_path = os.path.join(item_path, "papers_info.json")
            if os.path.isfile(file_path):
                try:
                    with open(file_path, "r") as json_file:
                        papers_info = json.load(json_file)
                        if paper_id in papers_info:
                            return json.dumps(papers_info[paper_id], indent=2)
                except (FileNotFoundError, json.JSONDecodeError) as e:
                    print(f"Error reading {file_path}: {str(e)}")
                    continue
    
    return f"There's no saved information related to paper {paper_id}."

@mcp.resource("papers://folders")
def get_available_folders() -> str:
    """
    List all available topic folders in the papers directory.
    
    This resource provides a simple list of all available topic folders.
    """
    folders = []
    
    # Get all topic directories
    if os.path.exists(PAPER_DIR):
        for topic_dir in os.listdir(PAPER_DIR):
            topic_path = os.path.join(PAPER_DIR, topic_dir)
            if os.path.isdir(topic_path):
                papers_file = os.path.join(topic_path, "papers_info.json")
                if os.path.exists(papers_file):
                    folders.append(topic_dir)
    
    # Create a simple markdown list
    content = "# Available Topics\n\n"
    if folders:
        for folder in folders:
            content += f"- {folder}\n"
        content += f"\nUse @{folder} to access papers in that topic.\n"
    else:
        content += "No topics found.\n"
    
    return content

@mcp.resource("papers://{topic}")
def get_topic_papers(topic: str) -> str:
    """
    Get detailed information about papers on a specific topic.
    
    Args:
        topic: The research topic to retrieve papers for
    """
    topic_dir = topic.lower().replace(" ", "_")
    papers_file = os.path.join(PAPER_DIR, topic_dir, "papers_info.json")
    
    if not os.path.exists(papers_file):
        return f"# No papers found for topic: {topic}\n\nTry searching for papers on this topic first."
    
    try:
        with open(papers_file, 'r') as f:
            papers_data = json.load(f)
        
        # Create markdown content with paper details
        content = f"# Papers on {topic.replace('_', ' ').title()}\n\n"
        content += f"Total papers: {len(papers_data)}\n\n"
        
        for paper_id, paper_info in papers_data.items():
            content += f"## {paper_info['title']}\n"
            content += f"- **Paper ID**: {paper_id}\n"
            content += f"- **Authors**: {', '.join(paper_info['authors'])}\n"
            content += f"- **Published**: {paper_info['published']}\n"
            content += f"- **PDF URL**: [{paper_info['pdf_url']}]({paper_info['pdf_url']})\n\n"
            content += f"### Summary\n{paper_info['summary'][:500]}...\n\n"
            content += "---\n\n"
        
        return content
    except json.JSONDecodeError:
        return f"# Error reading papers data for {topic}\n\nThe papers data file is corrupted."

@mcp.prompt()
def generate_search_prompt(topic: str, num_papers: int = 5) -> str:
    """Generate a prompt for Claude to find and discuss academic papers on a specific topic."""
    return f"""Search for {num_papers} academic papers about '{topic}' using the search_papers tool. 

Follow these instructions:
1. First, search for papers using search_papers(topic='{topic}', max_results={num_papers})
2. For each paper found, extract and organize the following information:
   - Paper title
   - Authors
   - Publication date
   - Brief summary of the key findings
   - Main contributions or innovations
   - Methodologies used
   - Relevance to the topic '{topic}'

3. Provide a comprehensive summary that includes:
   - Overview of the current state of research in '{topic}'
   - Common themes and trends across the papers
   - Key research gaps or areas for future investigation
   - Most impactful or influential papers in this area

4. Organize your findings in a clear, structured format with headings and bullet points for easy readability.

Please present both detailed information about each paper and a high-level synthesis of the research landscape in {topic}."""

if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')