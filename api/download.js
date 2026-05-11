import ytDlp from "yt-dlp-exec";

const COBALT_INSTANCES = [
  "https://cobalt.api.timelessnesses.me",
  "https://cobalt.synzr.space",
  "https://cob.frytki.pl",
  "https://cobalt.ggtyler.dev",
];

function isYouTube(url) {
  return /youtube\.com|youtu\.be/.test(url);
}

async function getYtDlpResult(videoUrl, quality) {
  const formatMap = {
    max:   "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "1080": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
    "720":  "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
    "480":  "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best",
    "360":  "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best",
    audio:  "bestaudio[ext=m4a]/bestaudio",
  };

  const format = formatMap[quality] || formatMap.max;

  const [urlResult, info] = await Promise.all([
    ytDlp(videoUrl, {
      getUrl: true,
      format,
      noWarnings: true,
      noCallHome: true,
      noCheckCertificates: true,
    }),
    ytDlp(videoUrl, {
      dumpSingleJson: true,
      noWarnings: true,
      noCallHome: true,
      skipDownload: true,
      format,
    }),
  ]);

  return {
    downloadUrl: typeof urlResult === "string" ? urlResult.trim().split("\n")[0] : null,
    title: info.title || "video",
    thumbnail: info.thumbnail || null,
    duration: info.duration || null,
    uploader: info.uploader || info.channel || null,
    platform: info.extractor_key || "YouTube",
  };
}

async function getCobaltUrl(videoUrl) {
  for (const instance of COBALT_INSTANCES) {
    try {
      const res = await fetch(`${instance}/api/json`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          url: videoUrl,
          vQuality: "max",
          filenamePattern: "basic",
        }),
        signal: AbortSignal.timeout(5000),
      });

      if (!res.ok) continue;
      const data = await res.json();

      if (data.status === "stream" || data.status === "redirect") {
        return { downloadUrl: data.url, instance };
      }
      if (data.status === "picker") {
        const videoItem = data.picker?.find((i) => i.type === "video");
        const url = videoItem?.url || data.picker?.[0]?.url;
        if (url) return { downloadUrl: url, instance };
      }
    } catch {
      continue;
    }
  }
  throw new Error("All Cobalt instances failed. The platform may be unsupported.");
}

export default async function handler(req, res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") return res.status(200).end();
  if (req.method !== "POST") return res.status(405).json({ error: "Method not allowed" });

  const { url, quality = "max" } = req.body || {};
  if (!url) return res.status(400).json({ error: "No URL provided" });

  try {
    if (isYouTube(url)) {
      const result = await getYtDlpResult(url, quality);
      if (!result.downloadUrl) throw new Error("yt-dlp returned no URL");
      return res.status(200).json({
        success: true,
        downloadUrl: result.downloadUrl,
        info: {
          title: result.title,
          thumbnail: result.thumbnail,
          duration: result.duration,
          uploader: result.uploader,
          source: "yt-dlp",
        },
      });
    } else {
      const result = await getCobaltUrl(url);
      return res.status(200).json({
        success: true,
        downloadUrl: result.downloadUrl,
        info: {
          title: "video",
          source: `cobalt (${result.instance})`,
        },
      });
    }
  } catch (err) {
    return res.status(500).json({
      success: false,
      error: err.message || "Download failed",
    });
  }
}
