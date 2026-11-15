Before: OpenSuperWhisper DB -> whisper_undo -> phrase history -> destroy. Handy DB -> (nothing).
After:  OpenSuperWhisper DB -> whisper_undo \
        Handy DB            -> handy_undo   -> shared trailing_insert -> phrase history -> destroy
