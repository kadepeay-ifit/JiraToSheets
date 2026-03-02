import matplotlib.pyplot as plt

def main():
    sizes = [15, 30, 45, 10]

    plt.pie(sizes, labels=['first', 'second', 'third', 'fourth'])

    plt.title('Pie Title')

    plt.show()

if __name__ == "__main__":
    main()
