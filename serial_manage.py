import serial
import serial.tools.list_ports

def update_port_list():
    """get list of available ports
    :return: list of available ports
    """
    print("Updating port list...")
    ports = serial.tools.list_ports.comports()
    port_list = []
    for port in ports:
        try:
            ser = serial.Serial(port.device)
            ser.close()
            print(f"Found port: {port.device}")
            port_list.append(port.device)
        except (OSError, serial.SerialException):
            print(f"Port {port.device} is occupied")
            pass
    return port_list