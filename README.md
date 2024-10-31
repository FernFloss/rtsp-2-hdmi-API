# rtsp-2-hdmi-API

RTSP-2-HDMI is a simple API for controlling the RTSP stream and sending it to HDMI output.

## How to use


## Endpoints

* `GET /status` - Get the status of the stream
* `POST /start` - Start the stream with the given url
* `POST /stop` - Stop the stream

## Examples

### Start example

Request:
```json
{
    "url": "rtsp://example.com/stream"
}
```
Response:
```json
{
    "status": "Preparing",
    "rtsp_url": "rtsp://example.com/stream"
}
```
### Stop example
Request:
```json
{
    "url": "rtsp://example.com/stream"
}
```
Response:
```json
{
    "status": "Stopped",
    "rtsp_url": "No stream"
}
```
### Status example

Request:
```json
{
    "url": "rtsp://example.com/stream"
}
```
Response:
```json
{
    "status": "Running",
    "rtsp_url": "rtsp://example.com/stream",
    "error_message": null
}
```
