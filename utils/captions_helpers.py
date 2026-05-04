from youtube_transcript_api import YouTubeTranscriptApi
from fugashi import Tagger

ytt_api=YouTubeTranscriptApi()


def fetch_raw_captions(video_id:str):
    snippets= ytt_api.fetch(video_id,languages=("ja",)).snippets
    return [{"index":i,"text":snippet.text,"start":snippet.start,"duration":snippet.duration} for i,snippet in enumerate(snippets)]

raw_captions=fetch_raw_captions("vZmCtYoIRLU")

from fugashi import Tagger

tagger = Tagger()
# text = "麩菓子は、麩を主材料とした日本の菓子。"
# tagger.parse(text)
# # => '麩 菓子 は 、 麩 を 主材 料 と し た 日本 の 菓子 。'
# for word in tagger(text):
#     print(word.surface, word.feature.lemma, word.pos, sep='\t')
#     # "feature" is the Unidic feature data as a named tuple


def tokenize_captions(raw_captions:list[dict]):
    for caption in raw_captions:
        caption["tokens"]=[token.surface for token in tagger(caption["text"])]
    return raw_captions

tokenized_caption=tokenize_captions(raw_captions)
print(tokenized_caption[10])
    