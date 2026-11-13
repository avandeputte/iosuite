# AI analysis

iopix can look at your photos and learn what is in them. **All of it runs on your own machine**, on the CPU, and the results are stored in iopix's own database. Nothing is written to digiKam, and no photo is sent to an outside service.

## What it adds

- **Content search**: find photos by describing them, and "more photos like this".
- **Objects**: people, animals, vehicles and everyday things, with boxes.
- **Text in photos**: signs, jerseys, documents, made searchable.
- **Photo descriptions**: one sentence per photo, or a short paragraph with Florence-2, searchable.
- **Places**: town, region and country from GPS positions.
- **Faces**: look-alike groups, "looks like" suggestions, and finding unmarked faces.
- **Photo quality**: sharpness, exposure, focus, an aesthetic score and closed eyes, to find the best shots and suggest rejects.
- **Date suggestions**: a year for photos whose date is unknown, from how old the people in them look, when those people are photographed, what the photo looks like and the camera.
- **Place suggestions**: where photos without a position were probably taken, from the photos around them that have one.
- **Jersey numbers**: the number on each player's shirt, searchable, and the player it suggests for someone whose face is not named.
- **Clothing matches**: within one event, who is probably in a photo by what they wear, when their face is not named.
- **Wrongly rotated**: photos stored on their side or upside down, with the lossless rotate that rights them.
- **Smart crop**: tiles and cards that crop a photo keep its subject (the faces, else the people) in the frame.
- **Videos**: a better cover frame, chapter thumbnails to jump to, and a searchable transcript of what is said.

Each is optional. Choose them during install, or later from **Settings › AI**.

## What it does not do

AI results are guesses, and iopix treats them that way:

- a suggested name is never written anywhere until you accept it,
- detected content is a filter, not stored tags,
- descriptions are shown with the AI analysis at the end of the info panel, never in place of your own caption,
- a likely reject is only a suggestion: no label is ever set on a photo,
- a suggested year, place or player is only saved when you click **Use** or **Tag**, and a photo that reads as turned is only rotated when you click **Rotate**.

## Background jobs

New and changed photos are picked up automatically. Heavy work goes through **one queue, one job at a time**, in this order: thumbnails, sharpness and objects, content search, text and face quality, face grouping, similar photos (on request), descriptions, photo quality, ages for date suggestions, jersey numbers, clothing matches, wrongly rotated photos, videos. The damaged-files check runs only when you start it.

Each job may use half the machine's cores by default (**Settings › AI**, or `BG_THREADS`), so iopix and everything else on the server stay responsive.

**Settings › AI** shows every job with its progress, **Check for new photos now** and **Run again from scratch**.

## Memory

The models are large, and a server has only so much memory. The jobs that load models therefore run in **a process of their own**, next to the web app: it starts when the first job needs it and ends when the queue is empty, which also gives the models' memory back.

iopix reads how much memory the server may use (the container's limit, where there is one) and checks once a second while a job runs:

- a job that takes more than its share (60% of the limit by default) is stopped,
- a job is stopped when the server as a whole has less than its reserve free (8% of the limit by default), and no job starts while memory is that short,
- the web app keeps running in every case, so the site stays up.

A job that was stopped is tried once more and continues from what it had finished. Stopped a second time, it is **paused**: Settings › AI shows why, with **Try again**. The same page shows the memory in use, and the last job that was stopped and when.

When a job is paused for memory, the usual cures are a smaller model for that feature (Settings › AI), more memory for the server, or fewer cores per job. `JOBS_MEMORY_MB` and `MEMORY_RESERVE_MB` change the two thresholds; see [Configuration](../reference/configuration.md).

## Turning it off

| Variable | Effect |
| --- | --- |
| `ANALYSIS=0` | no background analysis at all |
| `SEMANTIC=0` | no content search, even when installed |
| `CAPTIONS=0` | no photo descriptions |
