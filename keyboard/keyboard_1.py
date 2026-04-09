import curses

def main(stdscr):
  curses.curs_set(0)  # Hide the cursor
  
  stdscr.clear()  # Clear the screen
  stdscr.addstr(0, 0, "Key input detection...(Press ESC to exit)")
  stdscr.addstr(1, 0, "Press any key...")
  stdscr.refresh()  # Refresh the screen to show the text
  
  while True:
    key = stdscr.getch()  # Wait for a key press
    
    if key == 27:  # ESC key to exit
      break
    
    stdscr.clear()  # Clear the screen
    stdscr.addstr(0, 0, 'Key input detection...(Press ESC to exit)')
    
    if 32<= key <= 126:  # Printable characters
      stdscr.addstr(1, 0, f'Pressed key : {chr(key)}')
    else:
      stdscr.addstr(1, 0, f'Code : {key}')
      
    stdscr.refresh()  # Refresh the screen to show the updated text
    
curses.wrapper(main)  # Start the curses application