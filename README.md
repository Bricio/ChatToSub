# ChatToSub
Convert Extracted Chat From YT Into Subtitle (.srt)

# usage 
python extractor.py \<file\>
  
# Example
Download video and chat in json format. ( not made by this script )
```
yt-dlp EAR8DvHSH5w --write-subs --sub-lang live_chat -o "video_with_chat.%(ext)s"
```

Extract chat from json
```
python extractor.py video_with_chat.live_chat.json
```

It will generate the `video_with_chat.live_chat.json.str` file with the extracted chat.

# Behaviour

Script assumes the first chat was sent at the begining of transmission. 

It is up to you to sync with video it after the file is generated.
