
# You will need the following packages:
#    RPi
#    RPLCD

from RPi import GPIO
from RPLCD import CharLCD

# LCD configuration as on the PCB
rows   = 4
cols   = 20
pin_rs = 12
pin_e  = 16
pin_d4 = 19
pin_d5 = 20
pin_d6 = 26
pin_d7 = 21

class LCD(CharLCD):

    def __init__(self):
        super().__init__(cols=cols, rows=rows, pin_rs=pin_rs, pin_e=pin_e, pins_data=[pin_d4, pin_d5, pin_d6, pin_d7],
                         numbering_mode=GPIO.BCM)
        return

    def clear_display(self):
        for i in range(rows):
            self.cursor_position(i,0)
            self.write_string(u' ' * cols)
        return

    def display_data(self, setup='default', data):
        if (setup == 'default'):
            self.clear_display()
            self.cursor_position(0,0)
            self.write_string('Ta={:5.2f}'.format(data['Ta']))
            self.cursor_position(0,11)
            self.write_string('Pa={:6.1f}'.format(data['Pa']))
            self.cursor_position(1,0)
            self.write_string('Te={:5.2f}'.format(data['Te']))
            self.cursor_position(1,11)
            self.write_string('Pe={:6.1f}'.format(data['Pe']))
            self.cursor_position(2,0)
            self.write_string('Tw={:5.2f}'.format(data['Tw']))
            self.cursor_position(2,11)
            self.write_string('Pw={:6.1f}'.format(data['Pw']))
            self.cursor_position(3,0)
            self.write_string('Qw={:5.2f}'.format(data['Flow']))
            self.cursor_position(3,11)
            self.write_string('C={:6.1f}'.format(data['CO2']))
        else:
            pass
        return

# How to use...
#
#    lcd = LCD()
#    lcd.display_data('default', data)
#
# At shutdown:
#
#    lcd.close()
#



