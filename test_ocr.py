import asyncio
import io
from PIL import ImageGrab

from winrt.windows.storage.streams import InMemoryRandomAccessStream, DataWriter
from winrt.windows.graphics.imaging import BitmapDecoder
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.globalization import Language

async def test_memory_ocr():
    img = ImageGrab.grab(bbox=(0, 0, 500, 500))
    
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    data = img_byte_arr.getvalue()
    
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(data)
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)
    
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    
    lang = Language("en-US")
    engine = OcrEngine.try_create_from_language(lang)
    result = await engine.recognize_async(bitmap)
    print("Memory OCR Result:", result.text)

if __name__ == "__main__":
    asyncio.run(test_memory_ocr())
