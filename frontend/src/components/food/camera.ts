function isMediaStream(value: MediaProvider | null): value is MediaStream {
  return value !== null && typeof (value as MediaStream).getTracks === "function";
}

export function stopVideoTracks(video: HTMLVideoElement | null): void {
  const stream = video?.srcObject ?? null;
  if (isMediaStream(stream)) {
    stream.getTracks().forEach((track) => track.stop());
  }
  if (video) video.srcObject = null;
}
