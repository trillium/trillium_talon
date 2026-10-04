tag: user.pondering
-
^stop pondering$: user.pondering_disable()

^follow$: user.pondering_set_submit_method("follow")

^steer$: user.pondering_set_submit_method("steer")

key(escape): user.pondering_disable()
