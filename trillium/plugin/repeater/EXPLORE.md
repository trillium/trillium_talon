# Talon REPL Exploration

Goal: Get all the context of a command like `go up` so that we can pass correct params for `go down` as an opposite action.

## Test 1: Basic "go up" command

Say "go up" then run:

```python
a, b = actions.core.last_command()
print("a =", a)
print("a.trigger =", a.trigger)
print("b =", b)
print("type(b) =", type(b))
print("len(b) =", len(b))
print("b[0] =", b[0])
print("b[1] =", b[1])
print("type(b[1]) =", type(b[1]))
```

## Test 2: "go 5 word right" with count

Say "go 5 word right" then run:

```python
a, b = actions.core.last_command()
print("After 'go 5 word right':")
print("b =", b)
print("len(b) =", len(b))
for i, item in enumerate(b):
    print(f"  b[{i}] = {item}, type = {type(item)}")

# Access the NavigationStep object directly
nav_step = b[1]
print("\nNavigationStep details:")
print("nav_step =", nav_step)
print("nav_step.modifier =", nav_step.modifier)
print("nav_step.count =", nav_step.count)
```

## Test 3: Multiple steps "go left left up"

Say "go left left up" then run:

```python
mimic("go left left up")
a, b = actions.core.last_command()
print("After 'go left left up':")
print("b =", b)
print("len(b) =", len(b))
for i, item in enumerate(b):
    print(f"  b[{i}] = {item}, type = {type(item)}")

# Check if b[1] is a list of NavigationSteps
steps = b[1]
print("\nsteps =", steps)
print("type(steps) =", type(steps))
print("hasattr __iter__ =", hasattr(steps, '__iter__'))
try:
    for i, step in enumerate(steps):
        print(f"  step[{i}] = {step}, type = {type(step)}")
        print(f"    has modifier attr = {hasattr(step, 'modifier')}")
except:
    print("  steps not iterable, single item")
    print(f"  steps.modifier = {steps.modifier if hasattr(steps, 'modifier') else 'N/A'}")
    print(f"  steps.count = {steps.count if hasattr(steps, 'count') else 'N/A'}")
```

## Results will be pasted below:

```
>>>
>>>
>>> mimic("go left left up")
a, b = actions.core.last_command()
print("After 'go left left up':")
print("b =", b)
print("len(b) =", len(b))
for i, item in enumerate(b):
    print(f"  b[{i}] = {item}, type = {type(item)}")

# Check if b[1] is a list of NavigationSteps
steps = b[1]
print("\nsteps =", steps)
print("type(steps) =", type(steps))
print("hasattr __iter__ =", hasattr(steps, '__iter__'))
try:
    for i, step in enumerate(steps):
        print(f"  step[{i}] = {step}, type = {type(step)}")
        print(f"    has modifier attr = {hasattr(step, 'modifier')}")
except:
    print("  steps not iterable, single item")
    print(f"  steps.modifier = {steps.modifier if hasattr(steps, 'modifier') else 'N/A'}")
    print(f"  steps.count = {steps.count if hasattr(steps, 'count') else 'N/A'}")^[[D>>> a, b = actions.core.last_command()
>>> print("After 'go left left up':")
print("b =", b)
print("len(b) =", len(b))
for i, item in enumerate(b):
    print(f"  b[{i}] = {item}, type = {type(item)}")

# Check if b[1] is a list of NavigationSteps
steps = b[1]
print("\nsteps =", steps)
print("type(steps) =", type(steps))
print("hasattr __iter__ =", hasattr(steps, '__iter__'))
try:
    for i, step in enumerate(steps):
        print(f"  step[{i}] = {step}, type = {type(step)}")
        print(f"    has modifier attr = {hasattr(step, 'modifier')}")
except:
    print("  steps not iterable, single item")
    print(f"  steps.modifier = {steps.modifier if hasattr(steps, 'modifier') else 'N/A'}")
    print(f"  steps.count = {steps.count if hasattr(steps, 'count') else 'N/A'}")^[[D^[[D^[[AAfter 'go left left up':
>>> print("b =", b)
b = go NavigationStep(modifier='left', count=1) NavigationStep(modifier='left', count=1) NavigationStep(modifier='lineUp', count=1)
>>> print("len(b) =", len(b))
len(b) = 4
>>> for i, item in enumerate(b):
...     print(f"  b[{i}] = {item}, type = {type(item)}")
...
  b[0] = go, type = <class 'talon.engines.WordMeta'>
  b[1] = NavigationStep(modifier='left', count=1), type = <class 'user.__talon_community.core.edit.edit_navigation_steps.NavigationStep'>
  b[2] = NavigationStep(modifier='left', count=1), type = <class 'user.__talon_community.core.edit.edit_navigation_steps.NavigationStep'>
  b[3] = NavigationStep(modifier='lineUp', count=1), type = <class 'user.__talon_community.core.edit.edit_navigation_steps.NavigationStep'>
>>> # Check if b[1] is a list of NavigationSteps
>>> steps = b[1]
>>> print("\nsteps =", steps)

steps = NavigationStep(modifier='left', count=1)
>>> print("type(steps) =", type(steps))
type(steps) = <class 'user.__talon_community.core.edit.edit_navigation_steps.NavigationStep'>
>>> print("hasattr __iter__ =", hasattr(steps, '__iter__'))
hasattr __iter__ = False
>>> try:
...     for i, step in enumerate(steps):
...         print(f"  step[{i}] = {step}, type = {type(step)}")
...         print(f"    has modifier attr = {hasattr(step, 'modifier')}")
... except:
...     print("  steps not iterable, single item")
...     print(f"  steps.modifier = {steps.modifier if hasattr(steps, 'modifier') else 'N/A'}")
...     print(f"  steps.modifier = {steps.modifier if hasattr(steps, 'modifier') else 'N/A'}")
...
  steps not iterable, single item
  steps.modifier = left
  steps.modifier = left
>>>
>>>
>>>

```
