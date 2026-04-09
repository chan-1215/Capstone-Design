import curses

def main(stdscr):
  curses.curs_set(0)  # Hide the cursor
  msg = 'Ready! Press any key...'
  
  while True:
    stdscr.clear()  # Clear the screen
    
    stdscr.addstr(0, 0, 'Key input detection...(Press ESC to exit)')
    stdscr.addstr(1, 0, msg)
    stdscr.refresh()  # Refresh the screen to show the text
    
    key = stdscr.getch()  # Wait for a key press
    
    if key == ord('w'):  # ESC key to exit
      msg = 'Forward : w'
    elif key == ord('s'):
      msg = 'Backward : s'
    elif key == ord('a'):
      msg = 'Left Turn : a'
    elif key == ord('d'):
      msg = 'Right Turn : d'
    elif key == ord('q'):
      msg = 'Curve Left : q'
    elif key == ord('e'):
      msg = 'Curve Right : e'
    elif key == ord('+'):
      msg = 'Speed Up : +'
    elif key == ord('-'):
      msg = 'Speed Down : -'
    elif key == ' ':  # Space key to exit
      msg = 'Stop : space'
    elif key == 27:  # ESC key to exit
      break
    else:
      msg = f'Unknown key : {chr(key)}'

curses.wrapper(main)  # Start the curses application