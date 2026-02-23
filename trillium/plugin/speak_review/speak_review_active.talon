tag: user.speak_review_active
-

accept: user.speak_review_accept()
reject: user.speak_review_reject()
unnecessary: user.speak_review_unnecessary()
next: user.speak_review_next()
previous: user.speak_review_previous()
replay: user.speak_review_play()
regenerate: user.speak_review_regenerate()
review recent: user.speak_review_recent("")
review accepted: user.speak_review_recent("accepted")
review rejected: user.speak_review_recent("rejected")
review unnecessary: user.speak_review_recent("unnecessary")
review all: user.speak_review_recent("all")
fix <user.text>: user.speak_review_fix(text)
stop review: user.speak_review_stop()
