slash <user.slash_command>: "/{slash_command}"
slash <user.slash_command> (brave | bravely):
    insert("/{slash_command}")
    sleep(75ms)
    key(tab)
    key(enter)
