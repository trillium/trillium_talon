# Adding north east south west
west: edit.left()
east: edit.right()
north: edit.up()
south: edit.down()

# More east west
go line east: edit.line_start()
go line west: edit.line_end()

go line start | [go] head: edit.line_start()
go line end | [go] tail: edit.line_end()

nope: edit.undo()

file (save | safety): edit.save()
^(safety | disk)+$: edit.save()
