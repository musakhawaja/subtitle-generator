import streamlit as st
import ffmpeg
from openai import OpenAI
import os
from tempfile import NamedTemporaryFile
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

import re
from textwrap import wrap

def parse_time(time_str):
    """Converts a timestamp string to milliseconds."""
    hours, minutes, seconds_milliseconds = time_str.split(":")
    seconds, milliseconds = seconds_milliseconds.split(",")
    total_milliseconds = (int(hours) * 3600 + int(minutes) * 60 + int(seconds)) * 1000 + int(milliseconds)
    return total_milliseconds


def format_time(milliseconds):
    """Converts milliseconds to a timestamp string."""
    hours = milliseconds // 3600000
    minutes = (milliseconds % 3600000) // 60000
    seconds = (milliseconds % 60000) // 1000
    milliseconds = milliseconds % 1000
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def adjust_timestamps(start_ms, end_ms, parts):
    """Evenly splits the duration between start and end timestamps across the specified number of parts."""
    delta = (end_ms - start_ms) // parts
    timestamps = [(start_ms + i * delta, start_ms + (i + 1) * delta) for i in range(parts)]
    return timestamps

def split_subtitle_text(srt_text, max_length=40):
    segments = re.split('(\d+\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3})', srt_text.strip())
    segments = [segment for segment in segments if segment.strip() != '']  # Remove empty strings
    
    new_srt_text = ""
    subtitle_number = 1
    
    for i in range(0, len(segments), 2):
        header, text = segments[i:i+2]
        start_time, end_time = re.findall(r'\d{2}:\d{2}:\d{2},\d{3}', header)
        start_ms = parse_time(start_time)
        end_ms = parse_time(end_time)
        
        wrapped_lines = wrap(text, max_length)
        timestamps = adjust_timestamps(start_ms, end_ms, len(wrapped_lines))
        
        for j, line in enumerate(wrapped_lines):
            start, end = timestamps[j]
            new_srt_text += f"{subtitle_number}\n{format_time(start)} --> {format_time(end)}\n{line}\n\n"
            subtitle_number += 1
            
    return new_srt_text


def extract_audio_from_video(video_path):
    output_audio_path = NamedTemporaryFile(delete=False, suffix='.mp3').name
    (
        ffmpeg
        .input(video_path)
        .output(output_audio_path, audio_bitrate='192k', acodec='mp3')
        .run(overwrite_output=True, quiet=True)
    )
    return output_audio_path

def transcribe_audio(audio_path):
    with open(audio_path, 'rb') as audio:
        transcription_result = client.audio.transcriptions.create(
            model="whisper-1", 
            file=audio, 
            response_format="srt"
        )
    return transcription_result

def embed_subtitles_in_video(video_path, subtitles):
    output_video_path = NamedTemporaryFile(delete=False, suffix='.mp4').name
    (
        ffmpeg
        .input(video_path)
        .output(output_video_path, vf='subtitles=' + subtitles)
        .run(overwrite_output=True, quiet=True)
    )
    return output_video_path

def main():
    st.title('Subtitle Generator')

    uploaded_video = st.file_uploader("Choose a video...", type=['mp4', 'mov', 'avi', 'mkv'])
    if uploaded_video is not None:
        if 'original_video_path' not in st.session_state:
            video_file = NamedTemporaryFile(delete=False, suffix='.' + uploaded_video.name.split('.')[-1])
            video_file.write(uploaded_video.getvalue())
            video_file.close()
            st.session_state['original_video_path'] = video_file.name
        original_video_path = st.session_state['original_video_path']
        if 'transcription_done' not in st.session_state:
            if st.button('Transcribe Video'):
                with st.spinner('Extracting audio and transcribing...'):
                    audio_path = extract_audio_from_video(original_video_path)
                    transcription_result = transcribe_audio(audio_path)  # This should return the SRT text directly
                    
                    # Split subtitles to ensure each segment is within the character limit
                    # Directly pass transcription_result assuming it's the SRT text
                    splitted_subtitles = split_subtitle_text(transcription_result)  
                    st.session_state['subtitles'] = splitted_subtitles
                    st.session_state['transcription_done'] = True

                # Display video and subtitles side by side after transcription

        # The rest of your main function here...

        if 'transcription_done' in st.session_state:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Video")
                st.video(original_video_path)
            with col2:
                st.subheader("Generated Subtitles")
                st.session_state['edited_subtitles'] = st.text_area("Edit the subtitles here:", value=st.session_state['subtitles'], height=550)

            edited_subtitles = st.session_state.get('edited_subtitles', '')  # Ensure variable is defined
            if st.button('Save Edited Subtitles'):
                with NamedTemporaryFile(delete=False, mode='w', suffix='.srt') as subtitle_file:
                    subtitle_file.write(edited_subtitles)
                    subtitle_file.close()
                    edited_subtitles_path = subtitle_file.name

                with st.spinner('Embedding subtitles into video...'):
                    result_video_path = embed_subtitles_in_video(original_video_path, edited_subtitles_path)
                    st.session_state['result_video_path'] = result_video_path
                    st.session_state['subtitles_embedded'] = True

            if 'subtitles_embedded' in st.session_state and st.session_state['subtitles_embedded']:
                st.video(st.session_state['result_video_path'])
                with open(st.session_state['result_video_path'], "rb") as file:
                    st.download_button('Download Video', file, file_name='video_with_subtitles.mp4')
    else:
        st.session_state.clear()  # Reset state if no video is uploaded
        st.write("Upload a video and press 'Transcribe Video' to begin transcription.")

if __name__ == "__main__":
    main()

